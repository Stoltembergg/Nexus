/* Run only inside Riot main. Return non-private League patch state. */
(async () => {
  const fs = process.mainModule.require("fs");
  const path = process.mainModule.require("path");
  const https = process.mainModule.require("https");
  const argument = name => {
    const prefix = "--" + name + "=";
    const entry = process.argv.find(a => a.startsWith(prefix));
    if (entry) return entry.slice(prefix.length);
    const index = process.argv.indexOf("--" + name);
    return index >= 0 ? process.argv[index + 1] : undefined;
  };
  const port = Number(argument("app-port"));
  const token = argument("remoting-auth-token");
  if (!Number.isInteger(port) || !token) return {error: "Riot API unavailable"};
  const ca = fs.readFileSync(path.join(path.dirname(process.mainModule.filename), "root.pem"));
  const agent = new https.Agent({ca});
  const authorization = "Basic " + Buffer.from("riot:" + token).toString("base64");
  const get = resource => new Promise(resolve => {
    const req = https.request({hostname: "127.0.0.1", port, path: resource,
      agent, headers: {Authorization: authorization}}, res => {
      let body = "";
      res.on("data", c => {body += c; if (body.length > 10485760) req.destroy();});
      res.on("end", () => {
        try {resolve({code: res.statusCode, data: JSON.parse(body)});}
        catch {resolve({code: res.statusCode});}
      });
    });
    req.setTimeout(10000, () => req.destroy());
    req.on("error", () => resolve({error: "request failed"}));
    req.end();
  });
  const paths = ["/patch/v1/installs/league_of_legends.live",
    "/patch/v1/installs/league_of_legends.live.game_patch",
    "/product-metadata/v2/products/league_of_legends/patchlines/live",
    "/swagger/v2/swagger.json", "/patch/v1/installs"];
  const results = await Promise.all(paths.map(get));
  return results.map((r, i) => ({target: i, code: r.code, error: r.error,
    patch: r.data?.status?.patch?.state, install: r.data?.status?.install?.state,
    patchRequest: Boolean(r.data?.requests?.patch),
    installRequest: Boolean(r.data?.requests?.install),
    state: r.data?.state, type: r.data?.type,
    keys: r.data && Object.keys(r.data).filter(k => !/token|auth|user|account|path|url/i.test(k)),
    metadata: i === 2 && r.data ? {keys: Object.keys(r.data),
      tags: r.data.tags, hasPatchUrl: !!r.data.patch_url,
      patchHost: r.data.patch_url ? new URL(r.data.patch_url).hostname : undefined,
      cookieCount: r.data.content_cookies ? Object.keys(r.data.content_cookies).length : undefined,
      dependencies: r.data.dependencies?.map?.(d => ({id: d.id, keys: Object.keys(d)})),
      patchingKeys: r.data.patching_metadata && Object.keys(r.data.patching_metadata),
      installSizeBytes: r.data.install_size_bytes,
      configurationKeys: r.data.configuration && Object.keys(r.data.configuration),
      configurationType: typeof r.data.configuration,
      configurationShapes: r.data.configuration?.map?.(x => ({keys: Object.keys(x),
        id: x.id, type: x.type, product_id: x.product_id,
        install_id: x.install_id,
        children: x.dependencies?.map?.(d => ({keys: Object.keys(d), id: d.id}))})),
      productDependency: r.data.product_dependency && {keys: Object.keys(r.data.product_dependency), id: r.data.product_dependency.id},
      contentPathsKeys: r.data.content_paths && Object.keys(r.data.content_paths)} : undefined,
    schema: i === 3 && r.data ? {patchPaths: Object.keys(r.data.paths || {}).filter(k =>
      k.includes("/patch/v1/installs") && (k.includes("patch") || k.includes("install"))),
      definitions: Object.keys(r.data.definitions || {}).filter(k => /patch.*request|request.*patch|install/i.test(k)).slice(0, 40),
      patchRoute: r.data.paths?.["/patch/v1/installs/{install-id}/requests/patch"],
      patchRequestDefinition: r.data.definitions?.PatchPatchRequest} : undefined,
    installs: i === 4 && r.data ? {type: Array.isArray(r.data) ? "array" : typeof r.data,
      keys: Object.keys(r.data),
      values: (Array.isArray(r.data) ? r.data : Object.values(r.data)).map(x => typeof x === "string" ? x : ({id: x.id,
        keys: Object.keys(x), patch: x.status?.patch?.state, patchRequest: !!x.requests?.patch}))} : undefined}));
})()
