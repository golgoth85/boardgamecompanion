#!/usr/bin/env bash
set -euo pipefail

name='boardgamecompanion'

echo "lan_service_probe:"
for target in \
  "boardgamecompanion|http://192.168.1.55:8787/health" \
  "ollama_nas|http://192.168.1.55:11434/api/tags" \
  "ollama_pc|http://192.168.1.249:11434/api/tags"
do
  label="${target%%|*}"
  url="${target#*|}"
  if payload="$(curl -fsS --max-time 8 "$url" 2>&1)"; then
    echo "${label}_reachable=yes"
    if [[ "$label" == ollama_* ]]; then
      python3 -c 'import json,sys; p=json.load(sys.stdin); print("models="+",".join(sorted(str(x.get("name","")) for x in p.get("models",[]) if x.get("name"))))' <<<"$payload"
    else
      echo "${label}_payload=$payload"
    fi
  else
    echo "${label}_reachable=no"
    echo "${label}_error=$payload"
  fi
done

if ! command -v docker >/dev/null 2>&1; then
  echo "runtime_docker=UNAVAILABLE"
  exit 0
fi

if ! docker inspect "$name" >/dev/null 2>&1; then
  echo "runtime_container=NOT_FOUND"
  echo "matching_containers:"
  docker ps -a --format '{{.Names}}|{{.Image}}|{{.Ports}}|{{.Status}}' |
    grep -Ei 'boardgamecompanion|golgoth85/boardgamecompanion|8787' || true
  echo "matching_images:"
  docker image ls --digests --format '{{.Repository}}:{{.Tag}}|{{.Digest}}|{{.ID}}|{{.CreatedSince}}' |
    grep -Ei 'boardgamecompanion|golgoth85/boardgamecompanion' || true
  echo "host_health_probe:"
  if command -v curl >/dev/null 2>&1; then
    if payload="$(curl -fsS --max-time 5 http://127.0.0.1:8787/health 2>&1)"; then
      echo "host_health_status=200"
      echo "host_health_payload=$payload"
    else
      echo "host_health_error=$payload"
    fi
  else
    echo "host_health_error=curl_unavailable"
  fi
  exit 0
fi

echo "runtime_container=FOUND"
docker inspect "$name" --format 'container_name={{.Name}}'
docker inspect "$name" --format 'container_image_ref={{.Config.Image}}'
docker inspect "$name" --format 'container_image_id={{.Image}}'
docker inspect "$name" --format 'container_status={{.State.Status}}'
docker inspect "$name" --format 'container_started_at={{.State.StartedAt}}'
docker inspect "$name" --format 'container_restart={{.HostConfig.RestartPolicy.Name}}'
docker inspect "$name" --format 'container_network_mode={{.HostConfig.NetworkMode}}'
echo "container_ports:"
docker port "$name" || true
echo "container_mounts:"
docker inspect "$name" --format '{{range .Mounts}}{{.Source}} -> {{.Destination}} ({{.Mode}}){{println}}{{end}}'
echo "container_labels:"
docker inspect "$name" --format '{{range $k,$v := .Config.Labels}}{{println $k "=" $v}}{{end}}' |
  grep -E '^(com\.docker\.compose\.|net\.unraid\.|org\.opencontainers\.)' || true

echo "rag_environment_presence:"
for key in   BGC_OLLAMA_URL   BGC_OLLAMA_EMBEDDING_MODEL   BGC_OLLAMA_GENERATION_MODEL   BGC_OLLAMA_EMBEDDING_DIMENSIONS   BGC_OLLAMA_VERIFY_TLS
do
  if docker exec "$name" sh -c "test -n \"\${$key:-}\"" >/dev/null 2>&1; then
    echo "$key=SET"
  else
    echo "$key=UNSET"
  fi
done

echo "application_health:"
if payload="$(docker exec "$name" python -c 'import json,urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8787/health",timeout=5); print(r.status); print(json.dumps(json.load(r),sort_keys=True))' 2>&1)"; then
  echo "$payload" | sed -n '1s/^/health_status=/p;2s/^/health_payload=/p'
else
  echo "health_error=$payload"
fi

echo "ollama_runtime_probe:"
docker exec "$name" python -c '
import json, os, urllib.request
base=(os.getenv("BGC_OLLAMA_URL") or "").rstrip("/")
embed=os.getenv("BGC_OLLAMA_EMBEDDING_MODEL") or ""
generate=os.getenv("BGC_OLLAMA_GENERATION_MODEL") or ""
print("ollama_configured=" + ("yes" if base else "no"))
print("embedding_model_configured=" + ("yes" if embed else "no"))
print("generation_model_configured=" + ("yes" if generate else "no"))
if base:
    try:
        with urllib.request.urlopen(base + "/api/tags", timeout=8) as r:
            payload=json.load(r)
        names=sorted(str(item.get("name","")) for item in payload.get("models",[]) if item.get("name"))
        print("ollama_reachable=yes")
        print("ollama_models=" + ",".join(names))
        print("embedding_model_present=" + ("yes" if embed in names else "no"))
        print("generation_model_present=" + ("yes" if generate in names else "no"))
    except Exception as exc:
        print("ollama_reachable=no")
        print("ollama_error=" + type(exc).__name__ + ":" + str(exc))
'

echo "local_latest_image:"
image_ref="$(docker inspect "$name" --format '{{.Config.Image}}')"
if docker image inspect "$image_ref" >/dev/null 2>&1; then
  docker image inspect "$image_ref" --format 'local_image_id={{.Id}}'
  docker image inspect "$image_ref" --format 'local_image_created={{.Created}}'
  docker image inspect "$image_ref" --format 'local_image_repo_digests={{join .RepoDigests ","}}'
else
  echo "local_image=NOT_FOUND"
fi
