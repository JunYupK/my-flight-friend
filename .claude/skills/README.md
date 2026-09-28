# Vendored skills: superpowers

[obra/superpowers](https://github.com/obra/superpowers) 스킬을 플러그인 대신 프로젝트 스킬로 벤더링했다.
클라우드 세션에서 플러그인이 로드되지 않아, 레포에 포함시켜 모든 세션에서 바로 쓰도록 함.

- 출처: `obra/superpowers` v6.4.2 (commit `8ca22dba9a94f28898bbce59f2537ff4d87c747d`)
- 라이선스: MIT — [`LICENSE-superpowers`](./LICENSE-superpowers)
- 원본 파일은 수정하지 않음 (업데이트 시 그대로 덮어쓰기 위함)

## 포함 스킬 (14)

| 스킬 | 용도 |
|---|---|
| `brainstorming` | 구현 전 아이디어를 질문으로 구체화해 설계 확정 |
| `writing-plans` | 확정된 설계를 단계별 구현 계획으로 작성 |
| `executing-plans` | 작성된 계획을 체크포인트 단위로 실행 |
| `subagent-driven-development` | 계획의 태스크를 서브에이전트에 위임하고 리뷰 |
| `dispatching-parallel-agents` | 독립적인 작업을 병렬 에이전트로 분산 |
| `test-driven-development` | RED → GREEN → REFACTOR 사이클 |
| `systematic-debugging` | 근본 원인 추적 중심의 디버깅 절차 |
| `verification-before-completion` | 완료 주장 전 실제 검증 강제 |
| `requesting-code-review` | 작업 후 코드 리뷰 요청 |
| `receiving-code-review` | 리뷰 피드백 검증 후 반영 |
| `using-git-worktrees` | 격리된 워크트리에서 작업 |
| `finishing-a-development-branch` | 브랜치 마무리 (머지/PR/정리) |
| `writing-skills` | 새 스킬 작성·검증 |
| `using-superpowers` | 스킬 사용 규칙 (작업 시작 시 참고) |

제외: `diagnosing-superpowers` — 플러그인 설치 진단용이라 벤더링 환경에선 불필요.

## 플러그인과의 차이

- 스킬 이름에 접두어가 없다. 문서 안의 `superpowers:<name>` 참조는 `<name>` 스킬로 읽는다.
- 플러그인의 SessionStart 훅(`using-superpowers` 자동 주입)은 포함하지 않는다.

## 업데이트

```bash
git clone --depth 1 https://github.com/obra/superpowers.git /tmp/sp
for d in /tmp/sp/skills/*/; do
  n=$(basename "$d"); [ "$n" = diagnosing-superpowers ] && continue
  rm -rf ".claude/skills/$n" && cp -r "$d" ".claude/skills/$n"
done
cp /tmp/sp/LICENSE .claude/skills/LICENSE-superpowers
```

업데이트 후 위 버전/commit 표기를 갱신한다.
