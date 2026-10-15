<h1 align="center">dev-memory</h1>

<p align="center"><strong>開発習慣とプロジェクト規則を、新しい AI セッションでも使えるローカルメモリ。</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <a href="../../docs/readme/README.zh-CN.md">简体中文</a> · <strong>日本語</strong> · <a href="../../docs/readme/README.ko.md">한국어</a></p>

Dev Memory は、ユーザーが明示した要求、訂正、選択から再利用可能な開発習慣を学ぶ AI コーディングアシスタント向けのローカルメモリです。プロジェクト規則は各プロジェクトに分離し、記録、証拠、改訂履歴を SQLite に保存します。

## できること

- 後のセッションやプロジェクトで再利用できる、追跡・修正可能な習慣を蓄積します。
- 現在のタスクに関連する習慣と、許可されたプロジェクト規則だけを少量取得します。
- 一時的な指示は現在の会話に限定し、新規プロジェクト記録は既定で無効です。
- ホストの指示とローカル Python CLI で動作し、常駐プロセス、テレメトリー、外部メモリサービスはありません。

## クイックスタート

設定するプロジェクトのルートで実行します。`codex` は下表のホストパラメーターに置き換えられます。

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex
```

| AI ホスト | パラメーター |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness（DSH） | `deepseek` |

必要環境：Node.js 22+（npm/npx）、Git、Python 3.10+（sqlite3）。設定後、そのプロジェクトで新しい AI セッションを開始すれば使えます。毎回 Skill を呼び出したり保存を依頼したりする必要はありません。

Codex では、このコマンドでユーザー単位のグローバル習慣と現在のプロジェクト設定を構成します。他のホストは自動利用にプロジェクトごとの設定が必要です。未初期化プロジェクトでもユーザー指示を使えるのは現在 Codex のみです。DeepSeek はローカル DSH を指します。

## 記憶の範囲と既定値

| 記憶 | 例 | 範囲と既定値 |
| --- | --- | --- |
| グローバルな開発習慣 | 適切な既存実装の再利用、証拠に基づく調査、報告順序 | プロジェクト情報を除いて複数プロジェクトで使用。許可されたホスト設定で適格な学習を行います。 |
| プロジェクト規則 | 業務制約、設計判断、インターフェース規約 | 所有プロジェクトのみ。新規記録には `full-project` が必要です。 |
| 一時的な指示 | 「今回はテストを実行しないで」 | 現在の会話のみ。 |

新規プロジェクトは **`developer-first`** が既定です。既存規則は取得できますが、新しいプロジェクト記録は追加されません。長期的なプロジェクト記録には `full-project` を有効にします。アップグレード時は既存のデータと設定を保持します。

Codex のユーザー指示は、未初期化プロジェクトでもグローバル習慣を利用できますが、そのプロジェクトの業務情報を初期化・記録しません。別プロジェクトにも専用ストアと規則が必要な場合、そのルートでセットアップを実行します。初期化済みプロジェクトはグローバルと現在のプロジェクトを一度に取得します。

## 学習と取得の流れ

1. **取得：**タスク開始、再開、または実質的な話題変更時に、関連記憶を一度だけ範囲を限定して調べ、有効な結果を作業中に再利用します。
2. **学習：**明示された複数プロジェクト向けの好みは確認済み習慣になれます。繰り返すフィードバックは未適用候補から始まり、真に独立した二つのタスクの証拠でソフトな好みに昇格します。AI の要約や再取得はユーザー証拠になりません。
3. **修正・整理：**追加前に既存記録を確認し、訂正時は既存の習慣を改訂します。適切なタスク境界で範囲を限定して整理し、現在の指示を常に優先します。

ホストが非同期サブエージェントを提供する場合、読み取り専用の評価を開発と並行できます。メイン AI が範囲、プライバシー、設定を確認し、書き込みと保存結果の検証を行います。委譲できない場合はメイン AI が評価します。常時会話を監視する仕組みではありません。

## メモリの管理

| 目的 | AI への依頼例 |
| --- | --- |
| プロジェクト記録を有効化 | 「このプロジェクトを full-project に切り替えて」 |
| 既定モードへ戻す | 「このプロジェクトを developer-first に戻して」 |
| 習慣を修正 | 「要件に合う場合は既存実装を再利用するよう修正して」 |
| グローバル学習を一時停止 | 「グローバル習慣の書き込みを止め、取得は続けて」 |
| 今回を除外 | 「このターンの記憶は保存しないで」 |
| 確認・削除 | 「関連記憶を表示して」／「削除範囲を確認し、私の承認後に削除して」 |

## 保存先とプライバシー

| ストア | 既定の場所 |
| --- | --- |
| ユーザーのグローバル習慣 | `~/.dev-memory/global/` |
| 現在のプロジェクト規則 | `<project-root>/.dev-memory/` |

SQLite が正本で、Markdown は閲覧用です。ワークフローではグローバル記録からプロジェクト名、業務情報、コード、パス、認証情報、元の会話を除外します。プログラムは既知の機密・プロジェクト識別子を拒否しますが、意味上の匿名化は AI が行います。コアはストアをアップロードせず、テレメトリーも収集しません。ホストモデルに渡す抜粋にはホストのデータポリシーが適用されます。

## 検証とドキュメント

インストール成功は設定完了を示すもので、実際のホストセッションが指示に従うことの証明ではありません。Codex のプロジェクト間利用、非同期記録の完了、現行版の総タスク時間は実ホストでの検証が必要です。

[導入と削除](../../docs/installation.md) · [構成](../../docs/architecture.md) · [プロトコル](../../skills/dev-memory/references/protocol.md) · [検証報告](../../reports/verification.md) · [安全性](../../SECURITY.md) · [貢献](../../CONTRIBUTING.md)

機密情報を除いた問題を [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues) に報告してください。[MIT License](../../LICENSE) で公開しています。
