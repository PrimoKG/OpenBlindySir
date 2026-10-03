#!/bin/sh
# Docker + Compose are the only application runtimes required on the host.
set -eu
task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_data="$task_root/.local/docker"
task_env="$task_data/hosting.env"
task_action=${1:-start}
[ "$#" -eq 0 ] || shift
unset DOMAIN TLS_HOST HTTPS_PORT BIND_IP CADDY_PROFILE MUSIC_DIR BRIDGE_DEMO BRIDGE_ALLOW_FULL_REVIEW \
    BLIND_PASSWORD HOST_PASSWORD BRIDGE_SECRET BRIDGE_SECRETS COMPOSE_FILE COMPOSE_PROFILES COMPOSE_PROJECT_NAME
command -v docker >/dev/null 2>&1 || { echo 'Installez Docker avec Compose.' >&2; exit 2; }
cd "$task_root"
task_address=''
task_mode=private
task_music=''
task_demo=false
task_browser=true
task_build=true
while [ "$#" -gt 0 ]; do
    case "$1" in
        --address) task_address=$2; shift 2 ;;
        --mode) task_mode=$2; shift 2 ;;
        --music-dir) task_music=$2; shift 2 ;;
        --bridge-id) task_bridge_id=$2; shift 2 ;;
        --name) task_bridge_name=$2; shift 2 ;;
        --output) task_credential_output=$2; shift 2 ;;
        --demo) task_demo=true; shift ;;
        --no-browser) task_browser=false; shift ;;
        --no-build) task_build=false; shift ;;
        *) echo "Option inconnue : $1" >&2; exit 2 ;;
    esac
done
if [ "$task_action" = init ]; then
    [ ! -e "$task_env" ] || { echo 'Configuration existante : modifiez .local/docker/hosting.env.' >&2; exit 2; }
    [ -n "$task_address" ] || { echo 'Indiquez --address.' >&2; exit 2; }
    mkdir -p "$task_data"
    if [ "$task_demo" = true ]; then
        task_music="$task_data/demo-mount"
        mkdir -p "$task_music"
    fi
    [ -d "$task_music" ] || { echo 'Indiquez --music-dir avec un dossier existant, ou --demo.' >&2; exit 2; }
    task_music=$(CDPATH= cd -- "$task_music" && pwd)
    [ "$task_build" = false ] || docker build --target app --tag openblindysir-server:local .
    set -- docker run --rm --user "$(id -u):$(id -g)" --mount \
        "type=bind,source=$task_data,target=/setup" openblindysir-server:local \
        python /opt/tools/docker_config.py --address "$task_address" --mode "$task_mode" --music-dir "$task_music"
    [ "$task_demo" = false ] || set -- "$@" --demo
    "$@"
    echo 'Prêt : lancez sh tools/docker-host.sh start.'
    exit 0
fi
[ -f "$task_env" ] || { echo 'Utilisez init --address ... --music-dir ... (ou --demo).' >&2; exit 2; }
# Do not source a file containing passwords or personal paths as shell code.
task_domain=$(sed -n 's/^DOMAIN=//p' "$task_env")
task_profile=$(sed -n 's/^CADDY_PROFILE=//p' "$task_env")
task_url="https://$task_domain/host"
compose() {
    if [ "$task_profile" = public ]; then
        docker compose --env-file "$task_env" -f "$task_root/compose.yaml" -f "$task_root/deploy/compose.public.yaml" "$@"
    elif [ "$task_profile" = private ]; then
        docker compose --env-file "$task_env" -f "$task_root/compose.yaml" "$@"
    else
        echo 'CADDY_PROFILE doit être private ou public.' >&2; return 2
    fi
}
open_browser() {
    if [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$task_url" || echo "Ouvrez votre navigateur : $task_url"
    elif command -v open >/dev/null 2>&1; then open "$task_url" || echo "Ouvrez votre navigateur : $task_url"
    else echo "Ouvrez votre navigateur : $task_url"; fi
}
certificate() {
    [ "$task_profile" = private ] || { echo 'Le mode public utilise un certificat public.' >&2; return 2; }
    compose cp caddy:/data/caddy/pki/authorities/local/root.crt "$task_data/root.crt"
    echo "Certificat à approuver sur les appareils : $task_data/root.crt"
}
case "$task_action" in
    start)
        if [ "$task_build" = true ]; then compose up -d --build --wait --wait-timeout 120
        else compose up -d --wait --wait-timeout 120; fi
        echo "Partie : https://$task_domain"
        echo "Hôte : $task_url"
        [ "$task_profile" != private ] || certificate
        [ "$task_browser" = false ] || open_browser
        ;;
    stop) compose down ;;
    status) compose ps ;;
    bridge-credential)
        [ -n "${task_bridge_id:-}" ] && [ -n "${task_credential_output:-}" ] || {
            echo 'Indiquez --bridge-id UUID et --output /data/state/issued-NOM.toml.' >&2; exit 2;
        }
        compose exec -T app python -m openblindysir_server bridge-credential \
            --bridge-id "$task_bridge_id" --name "${task_bridge_name:-Bridge}" --output "$task_credential_output"
        echo 'Transférez le fichier privé au propriétaire de ce Bridge. Voir docs/v0.5.en.md.'
        ;;
    bridge-revoke)
        [ -n "${task_bridge_id:-}" ] || { echo 'Indiquez --bridge-id UUID.' >&2; exit 2; }
        compose exec -T app python -m openblindysir_server bridge-revoke --bridge-id "$task_bridge_id"
        ;;
    open) open_browser ;;
    certificate) certificate ;;
    *) echo 'Actions : init, start, stop, status, open, certificate, bridge-credential, bridge-revoke.' >&2; exit 2 ;;
esac
