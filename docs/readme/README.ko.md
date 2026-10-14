<h1 align="center">dev-memory</h1>

<p align="center"><strong>개발자 중심의 로컬 AI 개발 습관 기억 시스템.</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <a href="../../docs/readme/README.zh-CN.md">简体中文</a> · <a href="../../docs/readme/README.ja.md">日本語</a> · <strong>한국어</strong></p>
<p align="center"><a href="#기억이-형성되는-방식">기억이 형성되는 방식</a> · <a href="#설치">설치</a> · <a href="#일상적인-사용">일상적인 사용</a></p>

Dev Memory는 일상적인 코딩에서 표현한 요구사항, 정정, 기술적 결정과 작업 방식을 통해 학습합니다. 출처를 추적하고 수정할 수 있는 개발 습관과 사고 선호사항을 쌓아 프로젝트 간에 재사용합니다. 호스트 지침을 설정하면 AI는 새 프로젝트나 세션에서도 관련 습관을 조회해 분석, 구현과 검증·결과 보고에 적용할 수 있습니다.

## 기억이 형성되는 방식

1. **사용자 피드백에서 학습합니다.** 여러 프로젝트에 적용하는 명시적 습관은 확인된 규칙이 됩니다. 반복된 피드백은 후보로 저장되며 서로 다른 두 작업 ID의 근거로 소프트 선호사항이 될 수 있습니다. 실제로 독립적이고 재사용 가능한 피드백인지는 AI가 판단합니다.
2. **현재 작업에 맞춰 사용합니다.** 관련된 유효한 습관을 소수만 조회하고 조건과 예외를 고려해 적용합니다. 작업 내 유효한 문맥을 재사용하며 현재 사용자 지시를 우선합니다.
3. **정정에 따라 수정합니다.** 출처와 버전 이력을 유지하며 기존 습관을 갱신합니다. 완전한 중복은 프로그램이 감지하고 동의어 표현은 현재 AI가 판단합니다. AI의 요약이나 검색 횟수는 사용자 근거를 늘리지 않습니다.

| 개발자의 표현 | 처리 방식 |
| --- | --- |
| “앞으로 모든 프로젝트에서 새 구현을 추가하기 전에 기존 코드를 먼저 확인해 줘.” | 명시적인 전역 습관 |
| 독립적인 작업에서 반복해서 실제 근거를 확인한 뒤 수정하기를 선택 | 후보에서 근거가 있는 소프트 선호사항으로 전환 |
| “이 프로젝트의 결제 모듈은 수정하지 마.” | 프로젝트 기록을 켰을 때 저장하는 제약조건 |
| “이번에는 테스트를 실행하지 마.” | 이번 작업에만 적용 |

## 설치

프로젝트 루트에서 `<agent>`를 아래 표의 값으로 바꿔 실행하세요.

```sh
npx -y --prefer-online chrisstarr7/dev-memory <agent>
```

| AI 호스트 | `<agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness (DSH) | `deepseek` |

Node.js 22+(npm/npx), Git, Python 3.10+(sqlite3)가 필요합니다. 설치 프로그램은 런타임과 선택한 호스트의 프로젝트 지침을 설정합니다. 완료 후 **새 호스트 세션을 시작**하세요. 활성화한 프로젝트들은 같은 사용자의 전역 습관을 공유하고 프로젝트 기억은 각각 격리합니다. DeepSeek는 로컬 DSH를 의미하며 웹·모바일 채팅에서는 설치 프로그램을 실행할 수 없습니다.

**Codex는 사용자 수준 활성화도 지원합니다.** 다음 명령을 한 번 실행하면 프로젝트마다 초기화하지 않고 전역 습관을 사용할 수 있습니다.

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex --user
```

사용자 수준 활성화는 현재 Codex만 지원합니다. 다른 호스트는 프로젝트 어댑터를 사용합니다. 같은 설치 명령으로 관리되는 프로그램을 업데이트할 수 있으며 기억과 관련 없는 사용자 지침은 유지합니다. 오프라인 설치, 호스트 경로와 제거 방법은 [설치 안내](../../docs/installation.md)를 참고하세요.

## 일상적인 사용

설정 후 평소처럼 개발하세요. 현재 AI가 눈에 보이는 사용자 피드백에서 습관을 추출해 로컬 프로그램에 저장합니다. 백그라운드 대화 감시나 별도의 학습 모델은 없습니다.

| 제어 | AI에게 말하기 |
| --- | --- |
| 습관 수정 | “이 선호사항을 수정해 줘. 기존 구현은 요구사항에 맞을 때만 재사용해.” |
| 학습 일시 중지 | “전역 습관 쓰기는 중지하고 조회는 유지해 줘.” |
| 이번 턴 제외 | “이번 턴은 기억에 저장하지 마.” |
| 습관 삭제 | “삭제 범위를 보여 주고 내가 확인하면 삭제해 줘.” |

새 프로젝트는 **`developer-first`**가 기본입니다. 전역 습관을 우선하며 기존 프로젝트 기록은 조회하지만 새 업무 기록과 체크포인트는 추가하지 않습니다. 필요하면 AI에게 설치된 CLI를 `full-project`로 전환하도록 요청하세요. 자세한 방법은 [설치 안내](../../docs/installation.md)에 있습니다. 일반 개발에서는 필요한 기억만 조회하고 새 피드백을 묶어서 저장하며 매 턴 전체 프로필을 다시 만들지 않습니다.

## 로컬 저장과 제어

| 기억 | 기본 위치 |
| --- | --- |
| 전역 개발 습관 | `~/.dev-memory/global/` |
| 선택적 프로젝트 규칙과 체크포인트 | `<project-root>/.dev-memory/` |

SQLite는 개별 습관, 근거와 수정 이력을 저장하며 현재 유효한 습관들이 작업 프로필을 구성합니다. 멱등 쓰기, 격리, 백업, 읽기 전용 접근과 확인 후 삭제를 지원합니다. 전역 신호에서는 업무 내용을 제거해야 하며 프로젝트 이름, 업무 데이터, 코드, 경로와 원래 대화를 포함하면 안 됩니다. 핵심 프로그램은 기억을 업로드하거나 원격 측정 정보를 수집하지 않습니다. 모델 처리는 호스트의 데이터 정책을 따릅니다.

## 문서와 검증

런타임은 Python 표준 라이브러리와 SQLite를 사용합니다. 프로그램 테스트, 대화 의미 평가와 실제 호스트 검증을 별도로 기록합니다. 설치 성공은 설정을 확인한 것이며 자동 사용은 호스트의 지침 로딩과 AI의 준수에 달려 있습니다. 실제 Codex의 두 프로젝트에서 사용자 수준 지침이 자동 로드되는지와 비활성·구버전·신버전의 동일 작업 성능 비교는 아직 검증하지 않았습니다.

[구조](../../docs/architecture.md) · [프로토콜](../../skills/dev-memory/references/protocol.md) · [검증](../../reports/verification.md) · [0.7.0 작업 비교](../../reports/benchmark-0.7.0.md) · [보안](../../SECURITY.md) · [기여](../../CONTRIBUTING.md)

민감한 정보를 제거한 문제를 [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues)에 제보해 주세요. [MIT License](../../LICENSE)로 배포합니다.
