<h1 align="center">dev-memory</h1>

<p align="center"><strong>새 AI 세션에서도 개발 습관과 프로젝트 규칙을 이어 쓰는 로컬 기억.</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <a href="../../docs/readme/README.zh-CN.md">简体中文</a> · <a href="../../docs/readme/README.ja.md">日本語</a> · <strong>한국어</strong></p>

Dev Memory는 사용자가 명시한 요구, 수정 의견과 선택에서 재사용 가능한 개발 습관을 배우는 AI 코딩 도우미용 로컬 기억입니다. 프로젝트 규칙은 각 프로젝트에 보관하고, 기억·근거·수정 이력은 로컬 SQLite에 저장합니다.

## 기능

- 이후 세션과 프로젝트에서 재사용할 수 있는 추적 가능하고 수정 가능한 습관을 쌓습니다.
- 현재 작업에 관련된 습관과 허용된 프로젝트 규칙만 소량 조회합니다.
- 일회성 지시는 현재 대화에만 적용하며, 새 프로젝트 기억 기록은 기본적으로 꺼져 있습니다.
- 호스트 지침과 로컬 Python CLI로 작동하며 상주 프로세스, 원격 측정, 외부 기억 서비스가 없습니다.

## 빠른 시작

설정할 프로젝트 루트에서 실행하세요. 아래 표에 맞춰 `codex`를 호스트 매개변수로 바꾸면 됩니다.

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex
```

| AI 호스트 | 매개변수 |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness(DSH) | `deepseek` |

필요 환경: Node.js 22+(npm/npx), Git, Python 3.10+(sqlite3). 설정 후 해당 프로젝트에서 새 AI 세션을 시작하면 됩니다. 매번 Skill을 다시 호출하거나 기억 저장을 요청할 필요가 없습니다.

Codex에서는 이 명령이 사용자 수준의 전역 습관과 현재 프로젝트 연결을 함께 설정합니다. 다른 호스트는 자동 사용을 위해 프로젝트별 설정이 필요합니다. 초기화되지 않은 프로젝트에서도 사용자 수준 지침을 쓸 수 있는 호스트는 현재 Codex뿐입니다. DeepSeek는 로컬 DSH를 뜻합니다.

## 기억 범위와 기본값

| 기억 | 예시 | 범위와 기본값 |
| --- | --- | --- |
| 전역 개발 습관 | 적합한 기존 구현 재사용, 근거부터 조사하기, 결과 보고 순서 | 프로젝트 정보를 제거한 뒤 여러 프로젝트에서 사용합니다. 허용된 호스트 설정에서 적합한 학습을 수행합니다. |
| 프로젝트 규칙 | 업무 제약, 설계 결정, 인터페이스 약속 | 해당 프로젝트에만 적용합니다. 새 프로젝트 기록에는 `full-project`가 필요합니다. |
| 일회성 지시 | “이번에는 테스트를 실행하지 마.” | 현재 대화에만 적용합니다. |

새 프로젝트의 기본값은 **`developer-first`**입니다. 기존 규칙은 조회할 수 있지만 새 프로젝트 기억은 추가하지 않습니다. 장기 프로젝트 기록을 추가하려면 `full-project`로 전환하세요. 업그레이드 시 기존 데이터와 설정을 보존합니다.

Codex 사용자 지침은 초기화되지 않은 프로젝트에서도 전역 습관을 사용할 수 있지만, 해당 프로젝트의 업무 기억을 초기화하거나 기록하지 않습니다. 다른 프로젝트에 독립 저장소와 프로젝트 규칙이 필요하면 그 프로젝트 루트에서 설치 명령을 실행하세요. 초기화된 프로젝트는 전역과 현재 프로젝트 기억을 한 번에 조회합니다.

## 학습과 조회 방식

1. **조회:** 작업 시작·재개 또는 주제가 실질적으로 바뀔 때 한 번 제한된 조회를 하고, 유효한 결과는 작업 중 재사용합니다.
2. **학습:** 명시적인 프로젝트 공통 선호는 확인된 습관이 될 수 있습니다. 반복 피드백은 비활성 후보로 시작하며 실제로 독립된 두 작업의 근거가 있으면 소프트 선호로 승격됩니다. AI 요약과 반복 조회는 사용자 근거가 아닙니다.
3. **수정과 정리:** 새 기록 전에 기존 내용을 확인하고, 수정 요청이 있으면 기존 습관을 갱신합니다. 적절한 작업 경계에서 제한적으로 정리하며 현재 사용자 지시를 항상 우선합니다.

호스트가 비동기 하위 에이전트를 지원하면 읽기 전용 평가를 개발과 병행할 수 있습니다. 주 AI가 범위, 개인정보와 설정을 확인하고 모든 쓰기 및 저장 결과 검증을 담당합니다. 위임할 수 없으면 주 AI가 직접 평가합니다. 대화를 계속 감시하는 기능은 아닙니다.

## 기억 제어

| 목적 | AI에게 말하기 |
| --- | --- |
| 프로젝트 기록 켜기 | “현재 프로젝트를 full-project로 전환해 줘.” |
| 기본 모드로 돌아가기 | “현재 프로젝트를 developer-first로 전환해 줘.” |
| 습관 수정 | “요구사항에 맞는 경우 기존 구현을 재사용하도록 수정해 줘.” |
| 전역 학습 일시 중지 | “전역 습관 쓰기는 멈추고 조회는 유지해 줘.” |
| 이번 턴 제외 | “이번 턴은 기억에 저장하지 마.” |
| 확인 또는 삭제 | “관련 기억을 보여 줘.” / “삭제 범위를 미리 보고 확인 후 삭제해 줘.” |

## 저장 위치와 개인정보

| 저장소 | 기본 위치 |
| --- | --- |
| 사용자 전역 습관 | `~/.dev-memory/global/` |
| 현재 프로젝트 규칙 | `<project-root>/.dev-memory/` |

SQLite가 기준 데이터이며 Markdown은 읽기용입니다. 작업 절차는 전역 기록에서 프로젝트 이름, 업무 내용, 코드, 경로, 인증 정보와 원문 대화를 제외합니다. 프로그램은 알려진 민감 정보와 프로젝트 식별자를 차단하지만 의미상 비식별화는 AI가 담당합니다. 핵심 프로그램은 저장소를 업로드하거나 원격 측정을 수집하지 않습니다. 호스트 모델에 전달한 발췌문에는 해당 호스트의 데이터 정책이 적용됩니다.

## 검증과 문서

설치 성공은 설정 완료를 뜻할 뿐 실제 호스트 세션이 지침을 따른다는 증거는 아닙니다. Codex 프로젝트 간 사용, 비동기 기록 완료와 현재 버전의 전체 작업 시간은 실제 호스트 검증이 필요합니다.

[설치와 제거](../../docs/installation.md) · [구조](../../docs/architecture.md) · [프로토콜](../../skills/dev-memory/references/protocol.md) · [검증 보고](../../reports/verification.md) · [보안](../../SECURITY.md) · [기여](../../CONTRIBUTING.md)

민감 정보를 제거한 문제를 [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues)에 보고해 주세요. [MIT License](../../LICENSE)로 배포합니다.
