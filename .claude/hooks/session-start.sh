#!/bin/bash
# SessionStart hook: .env에서 MCP_API_KEY를 읽어 settings.json에 MCP 서버 설정 주입

# 1) 환경변수에서 먼저 확인 (Claude Code 웹 Environment 설정)
# 2) 없으면 .env 파일에서 읽기 (로컬/OCI 서버)
MCP_KEY="${MCP_API_KEY:-$(grep '^MCP_API_KEY=' .env 2>/dev/null | cut -d= -f2)}"
if [ -z "$MCP_KEY" ]; then
  echo "[session-start] MCP_API_KEY not found, skipping MCP setup"
  exit 0
fi

export MCP_KEY

python3 -c "
import json, pathlib, os

key = os.environ['MCP_KEY']
p = pathlib.Path('.claude/settings.json')
cfg = json.loads(p.read_text()) if p.exists() else {}
cfg['mcpServers'] = {
    'flight-friend': {
        'type': 'sse',
        'url': 'https://flight-friend.com/mcp/sse',
        'headers': {'Authorization': f'Bearer {key}'}
    }
}
p.write_text(json.dumps(cfg, indent=2) + '\n')
print('[session-start] MCP server configured')
" 2>&1

exit 0
