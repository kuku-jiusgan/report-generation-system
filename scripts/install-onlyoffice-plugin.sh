#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
container_id="$(docker ps --filter publish=8090 --format '{{.ID}}' | head -n 1)"
plugin_guid="{B75A5F24-8D2C-4E91-A763-6C98B8B80A15}"
plugin_root="/var/www/onlyoffice/documentserver/sdkjs-plugins/${plugin_guid}"
public_base_url="$(sed -n 's/^REPORT_PUBLIC_BASE_URL=//p' "${project_root}/.env" | tail -n 1)"
rendered_config="$(mktemp)"
trap 'rm -f "${rendered_config}"' EXIT

if [[ -z "${container_id}" ]]; then
  echo "No running ONLYOFFICE container publishing port 8090 was found." >&2
  exit 1
fi

docker exec "${container_id}" mkdir -p "${plugin_root}"
sed "s#__REPORT_PUBLIC_BASE_URL__#${public_base_url%/}#g" \
  "${project_root}/deploy/onlyoffice-plugin/config.json" > "${rendered_config}"
chmod 0644 "${rendered_config}"
docker cp "${rendered_config}" "${container_id}:${plugin_root}/config.json"
docker cp "${project_root}/deploy/onlyoffice-plugin/index.html" "${container_id}:${plugin_root}/index.html"
docker cp "${project_root}/frontend/public/onlyoffice-template-link/link.js" "${container_id}:${plugin_root}/link.js"
docker exec "${container_id}" mkdir -p "${plugin_root}/translations"
docker cp "${project_root}/deploy/onlyoffice-plugin/translations/langs.json" "${container_id}:${plugin_root}/translations/langs.json"
docker cp "${project_root}/deploy/onlyoffice-plugin/translations/zh-CN.json" "${container_id}:${plugin_root}/translations/zh-CN.json"
docker exec "${container_id}" chmod 0644 \
  "${plugin_root}/config.json" "${plugin_root}/index.html" "${plugin_root}/link.js" \
  "${plugin_root}/translations/langs.json" "${plugin_root}/translations/zh-CN.json"
docker restart "${container_id}" >/dev/null

docker exec "${container_id}" grep -q '"version": "1.0.15"' "${plugin_root}/config.json"
docker exec "${container_id}" grep -q '"serviceUrl": "http' "${plugin_root}/config.json"
docker exec "${container_id}" grep -q "executeMethod('SelectContentControl'" "${plugin_root}/link.js"
docker exec "${container_id}" grep -q "executeMethod('MoveCursorToContentControl'" "${plugin_root}/link.js"
docker exec "${container_id}" grep -q "command.type === 'bind'" "${plugin_root}/link.js"

plugin_url="http://127.0.0.1:8090/sdkjs-plugins/%7BB75A5F24-8D2C-4E91-A763-6C98B8B80A15%7D/config.json?v=18"
for _ in {1..30}; do
  if curl -fsS "${plugin_url}" | grep -q '"version": "1.0.15"'; then
    echo "Installed and verified Report Template Link 1.0.15 in ONLYOFFICE container ${container_id}."
    exit 0
  fi
  sleep 1
done
echo "Plugin files were copied, but ONLYOFFICE did not serve version 1.0.15." >&2
exit 1
