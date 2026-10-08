#!/usr/bin/env bash
# Start Label Studio locally (private: nothing leaves this computer), serving frames from ml/data.
# First run creates ml/.labelstudio.env with your local login. Then open http://localhost:8090
set -euo pipefail
ML="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ML/.labelstudio.env"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  {
    echo "LABEL_STUDIO_USERNAME=${LABEL_STUDIO_USERNAME:-arnavmani01@gmail.com}"
    echo "LABEL_STUDIO_PASSWORD=$(openssl rand -base64 18 | tr -d '/+=')"
  } > "$ENV_FILE"
  echo "Created $ENV_FILE with your Label Studio login."
fi
set -a; source "$ENV_FILE"; set +a
export LABEL_STUDIO_LOCAL_FILES_SERVING_ENABLED=true
export LABEL_STUDIO_LOCAL_FILES_DOCUMENT_ROOT="$ML/data"
exec "$ML/.venv-labelstudio/bin/label-studio" start --port 8090 --no-browser \
  --username "$LABEL_STUDIO_USERNAME" --password "$LABEL_STUDIO_PASSWORD"
