/* Request an ordinary League launch through Riot's local product launcher. */
(async () => {
  const fs = process.mainModule.require("fs");
  const path = process.mainModule.require("path");
  const https = process.mainModule.require("https");
  const argument = name => {
    const prefix = "--" + name + "=";
    const entry = process.argv.find(a => a.startsWith(prefix));
    if (entry) return entry.slice(prefix.length);
    const i = process.argv.indexOf("--" + name);
    return i >= 0 ? process.argv[i + 1] : undefined;
  };
  const port = Number(argument("app-port")), token = argument("remoting-auth-token");
  if (!Number.isInteger(port) || !token) return {error: "Riot API unavailable"};
  const ca = fs.readFileSync(path.join(path.dirname(process.mainModule.filename), "root.pem"));
  const agent = new https.Agent({ca});
  const authorization = "Basic " + Buffer.from("riot:" + token).toString("base64");
  const request = (method, resource, body) => new Promise(resolve => {
    const payload = JSON.stringify(body);
    const req = https.request({hostname: "127.0.0.1", port,
      path: resource, method, agent, headers: {Authorization: authorization,
        "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload)}}, res => {
      res.resume(); res.on("end", () => resolve({status: res.statusCode}));
    });
    req.setTimeout(30000, () => req.destroy());
    req.on("error", () => resolve({error: "launch request failed"}));
    req.end(payload);
  });
  const context = await request("PUT", "/player-session-lifecycle/v1/product-context",
    {productContext: {productId: "league_of_legends", patchlineId: "live"}});
  if (context.error || context.status >= 300) return {step: "context", ...context};
  await request("POST", "/data-store/v1/install-settings/riot-client-app-command/upgrade_attempts", 0);
  for (let attempt = 0; attempt < 3; ++attempt) {
    const launch = await request("POST", "/product-launcher/v1/products/league_of_legends/patchlines/live", {});
    if (launch.status !== 424 || attempt === 2) return launch;
    await new Promise(resolve => setTimeout(resolve, 5000));
  }
})()
