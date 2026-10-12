/* Repair accepted League Update actions; reconcile status only after both installs finish. */
(() => {
  const e = process.mainModule.require("electron");
  if (!e.app.getName().toLowerCase().includes("riot")) return false;
  if (global.__darlingLeagueUpdate && global.__darlingLeagueUpdate.version >= 9) return true;
  const fs = process.mainModule.require("fs"), path = process.mainModule.require("path");
  const https = process.mainModule.require("https");
  const argument = name => {
    const prefix = "--" + name + "=";
    const entry = process.argv.find(a => a.startsWith(prefix));
    if (entry) return entry.slice(prefix.length);
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : undefined;
  };
  const port = Number(argument("app-port")), token = argument("remoting-auth-token");
  if (!Number.isInteger(port) || port < 1 || port > 65535 || !token) return false;
  const ca = fs.readFileSync(path.join(path.dirname(process.mainModule.filename), "root.pem"));
  const agent = new https.Agent({ca});
  const authorization = "Basic " + Buffer.from("riot:" + token).toString("base64");
  const request = (resource, method = "GET", data) => new Promise((resolve, reject) => {
    const body = data === undefined ? "" : JSON.stringify(data);
    const req = https.request({hostname: "127.0.0.1", port, path: resource, method, agent,
      headers: {Authorization: authorization, "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body)}}, res => {
      let result = "";
      res.on("data", chunk => {result += chunk; if (result.length > 1048576) req.destroy();});
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error("Patch API failed " + res.statusCode));
        try {resolve(result ? JSON.parse(result) : null);} catch {reject(new Error("Invalid patch response"));}
      });
    });
    req.setTimeout(15000, () => req.destroy(new Error("Patch API timeout")));
    req.on("error", reject); req.end(body);
  });
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const patchable = state => state === "out_of_date" || state === "not_installed";
  const installIds = ["league_of_legends.live", "league_of_legends.live.game_patch"];
  const ownedPatches = new Map();
  const normalizeGameRoot = async install => {
    const nativeGame = "/Applications/League of Legends.app/Contents/LoL/Game";
    if (install.path !== "/Applications/League of Legends.app/Game" || install.requests?.patch
        || !fs.existsSync(nativeGame + "/LeagueofLegends.app/Contents/MacOS/LeagueofLegends")) return;
    await request("/patch/v1/installs/" + installIds[1], "PUT", {
      path: nativeGame, metadata_path: install.metadata_path, seed_path: install.seed_path,
      excluded_paths: install.excluded_paths, ipv4_only: install.ipv4_only});
    install.path = nativeGame;
  };
  /* Submit a patch request for one install. URL must be Riot's CDN; the manifest
     URL comes from the install's own recorded state when present, otherwise from
     the live mac game release from Patchsieve (the game install always uses it). Never deletes
     foreign paths and never touches requests already in flight. */
  const repairInstall = async (installId, fallback) => {
    const install = await request("/patch/v1/installs/" + installId);
    if (installId === installIds[1]) await normalizeGameRoot(install);
    const patch = install.status?.patch;
    // An authoritative fallback (the live release) wins over the install's recorded URL, which can
    // be empty or point at an older release.
    const recorded = patch?.url && typeof patch.url === "string" && patch.url.startsWith("https://") ? patch.url : null;
    // An install recorded as up to date at some other release (for example after repairing to an
    // outdated manifest) is also patched, so it converges back to the live release.
    const behind = fallback.authoritative && patch?.state === "up_to_date" && recorded;
    if (!(patchable(patch?.state) || behind) || install.requests?.patch) return "skipped";
    const url = fallback.authoritative || !recorded ? await fallback.url() : recorded;
    if (behind && url === recorded) return "skipped";
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || !parsed.hostname.endsWith(".riotcdn.net")) throw new Error("Unexpected patch host");
    const tags = Array.isArray(patch?.tags) && patch.tags.length ? patch.tags : await fallback.tags();
    // The secondary root is relative to the product bundle in Riot's metadata,
    // but the mac game lives under Contents/LoL. A client update can remove an
    // alias at the bundle root. Register the real directory before game repair.
    await request("/patch/v1/installs/" + installId + "/requests/patch", "PUT", {
      url, headers: {}, tags, repair: false, delete_foreign_paths: false,
      max_download_speed: 0});
    ownedPatches.set(installId, {url, tags: JSON.stringify(tags)});
    return "submitted";
  };
  /* The live mac game release, from the same Patchsieve query the League client makes. The local
     ClientConfiguration.json is not used: it can name a release years older than the client, and
     repairing to it replaces the game with that old build. */
  const sieveVersionSets = {EUW: "EUW1", EUNE: "EUN1", EUN: "EUN1", NA: "NA1", BR: "BR1", LAN: "LA1",
    LAS: "LA2", OCE: "OC1", TR: "TR1", RU: "RU", JP: "JP1", KR: "KR"};
  const sieveGet = resource => new Promise((resolve, reject) => {
    const req = https.request({hostname: "sieve.services.riotcdn.net", path: resource, method: "GET"}, res => {
      let result = "";
      res.on("data", chunk => {result += chunk; if (result.length > 1048576) req.destroy();});
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return reject(new Error("Patchsieve failed " + res.statusCode));
        try {resolve(JSON.parse(result));} catch {reject(new Error("Invalid Patchsieve response"));}
      });
    });
    req.setTimeout(15000, () => req.destroy(new Error("Patchsieve timeout")));
    req.on("error", reject); req.end();
  });
  const liveGameUrl = async () => {
    const locale = await request("/riotclient/region-locale");
    const versionSet = sieveVersionSets[String(locale?.region || "").toUpperCase()];
    if (!versionSet) throw new Error("Unknown region for Patchsieve");
    const sieve = await sieveGet("/api/v1/products/lol/version-sets/" + versionSet +
      "?q[artifact_type_id]=lol-game-client&q[platform]=macos&q[published]=true");
    const releases = (sieve?.releases || []).filter(r => r?.download?.scd_required === false
      && /^https:\/\/[a-z0-9.-]+\.riotcdn\.net\/channels\/public\/releases\/[0-9A-F]{16}\.manifest$/.test(r.download.url || ""));
    if (!releases.length) throw new Error("No live game release in Patchsieve");
    releases.sort((a, b) => String(b.release?.created_at).localeCompare(String(a.release?.created_at)));
    return releases[0].download.url;
  };
  const fallbackClientUrl = async () => {
    const metadata = await request("/product-metadata/v2/products/league_of_legends/patchlines/live");
    // Protected manifests must use Riot's normal cookie handling.
    if (metadata.content_cookies && Object.keys(metadata.content_cookies).length) throw new Error("Protected manifest");
    return metadata.patch_url;
  };
  const clientFallback = {url: fallbackClientUrl, tags: async () => []};
  const gameFallback = {
    url: liveGameUrl, authoritative: true,
    tags: async () => {
      const client = await request("/patch/v1/installs/league_of_legends.live");
      return Array.isArray(client.status?.patch?.tags) ? client.status.patch.tags : [];
    }};
  const appUpdateStale = async () => {
    try {
      const status = await request("/product-integration-deps/v1/app-update/statuses/products/league_of_legends/patchlines/live");
      return status?.updateAvailable === true;
    } catch {return false;}
  };
  const installsReady = async () => {
    const installs = await Promise.all(installIds.map(id => request("/patch/v1/installs/" + id)));
    for (let index = 0; index < installs.length; index++) {
      const install = installs[index], owned = ownedPatches.get(installIds[index]);
      const current = install.requests?.patch;
      // A completed legacy request remains registered until explicitly removed.
      // Clear only this hook's unchanged request after the updater finishes.
      if (install.status?.patch?.state === "up_to_date" && owned && current
          && current.url === owned.url && JSON.stringify(current.tags) === owned.tags) {
        await request("/patch/v1/installs/" + installIds[index] + "/requests/patch", "DELETE");
        ownedPatches.delete(installIds[index]);
        install.requests.patch = null;
      }
    }
    return installs.every(i => i.status?.patch?.state === "up_to_date" && !i.requests?.patch);
  };
  const clearStaleStatus = async () => {
    if (!(await installsReady())) return false;
    if (!(await appUpdateStale())) return true;
    await request("/product-integration-deps/v1/app-update/statuses/products/league_of_legends/patchlines/live",
      "PUT", {updateAvailable: false, updateRequired: false});
    return true;
  };
  const state = {version: 9, pending: false, rootPending: true, rootError: false,
    submitted: 0, failed: 0, last: null, convergence: null};
  // Riot's startup integrity pass can replace the bundle-root alias with an
  // empty directory. Bind the updater to the real files before the user clicks
  // Update or Play, including when no update action is needed.
  const rootReady = request("/patch/v1/installs/" + installIds[1])
    .then(normalizeGameRoot).catch(() => {state.rootError = true;})
    .finally(() => {state.rootPending = false;});
  const repairHandoff = async () => {
    try {
      await rootReady;
      const results = {};
      results.client = await repairInstall("league_of_legends.live", clientFallback);
      results.game = await repairInstall("league_of_legends.live.game_patch", gameFallback);
      state.last = results;
      if (Object.values(results).some(r => r === "submitted")) state.submitted++;
      state.convergence = "waiting";
      // Keep readiness honest while the updater downloads or verifies files.
      for (let attempt = 0; attempt < 60; attempt++) {
        if (await clearStaleStatus()) {state.convergence = "ready"; return;}
        await sleep(10000);
      }
      state.convergence = "unfinished";
    } catch {state.failed++; state.convergence = "error";}
    finally {state.pending = false;}
  };
  global.__darlingLeagueRepairNow = async () => {
    if (state.pending) return {busy: true};
    state.pending = true;
    setTimeout(repairHandoff, 0);
    return {queued: true};
  };
  e.session.defaultSession.webRequest.onCompleted({urls: ["http://127.0.0.1/*", "https://127.0.0.1/*"]}, details => {
    if (details.statusCode !== 204 || state.pending) return;
    if (new URL(details.url).pathname !== "/patch-proxy/v2/priority-patch/products/league_of_legends/patchlines/live") return;
    state.pending = true; setTimeout(repairHandoff, 5000);
  });
  global.__darlingLeagueUpdate = state;
  return true;
})()
