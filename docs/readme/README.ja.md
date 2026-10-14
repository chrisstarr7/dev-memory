<h1 align="center">dev-memory</h1>

<p align="center"><strong>開発者を中心とした、ローカルの AI 開発習慣メモリ。</strong></p>

<p align="center">
  <a href="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml"><img src="https://github.com/chrisstarr7/dev-memory/actions/workflows/check.yml/badge.svg" alt="Program checks" /></a>
  <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-08C" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB" alt="Python 3.10 or newer" />
  <img src="https://img.shields.io/badge/storage-local%20SQLite-4493F8" alt="Local SQLite storage" />
</p>

<p align="center"><a href="../../README.md">English</a> · <a href="../../docs/readme/README.zh-CN.md">简体中文</a> · <strong>日本語</strong> · <a href="../../docs/readme/README.ko.md">한국어</a></p>
<p align="center"><a href="#記憶の仕組み">記憶の仕組み</a> · <a href="#インストール">インストール</a> · <a href="#日常の使い方">日常の使い方</a></p>

Dev Memory は、日々のコーディングで示された要望、訂正、技術的な判断、作業方法から学びます。出典を追跡でき、修正できる開発習慣や思考上の好みを蓄積し、プロジェクト間で再利用します。ホストの指示を設定すると、AI は新しいプロジェクトやセッションでも関連する習慣を取得し、分析、実装、検証・成果報告に適用できます。

## 記憶の仕組み

1. **ユーザーの反応から学ぶ。** 複数プロジェクトに適用する明示的な習慣は確認済みルールになります。繰り返された反応は候補となり、異なる二つのタスク ID の証拠でソフトな好みに昇格できます。反応が独立していて再利用可能かは AI が判断します。
2. **タスクに応じて使う。** 少数の関連する有効な習慣を取得し、条件と例外を考慮して適用します。タスク内で有効な文脈を再利用し、現在のユーザー指示を優先します。
3. **訂正に基づいて改訂する。** 出典と版の履歴を残して既存の習慣を更新します。完全一致はプログラムが検出し、言い換えは現在の AI が判断します。AI の要約や検索ヒットはユーザーの証拠を増やしません。

| 開発者の表現 | 扱い |
| --- | --- |
| 「今後どのプロジェクトでも、新しい実装を加える前に既存コードを確認して」 | 明示的なグローバル習慣 |
| 独立したタスクで繰り返し、証拠を確認してから修正する方法を選ぶ | 候補から証拠に基づくソフトな好みへ |
| 「このプロジェクトの決済モジュールは変更しないで」 | プロジェクト記録が有効な場合の制約 |
| 「今回はテストを実行しないで」 | 今回のタスクのみの指示 |

## インストール

プロジェクトのルートで、`<agent>` を下表の値に置き換えて実行します。

```sh
npx -y --prefer-online chrisstarr7/dev-memory <agent>
```

| AI ホスト | `<agent>` |
| --- | --- |
| Codex | `codex` |
| Claude Code | `claude` |
| Cursor | `cursor` |
| Gemini CLI | `gemini` |
| GitHub Copilot | `copilot` |
| OpenCode | `opencode` |
| DeepSeek Harness（DSH） | `deepseek` |

Node.js 22+（npm/npx）、Git、Python 3.10+（sqlite3）が必要です。インストーラーは実行プログラムとホストのプロジェクト指示を設定します。完了後は**新しいホストセッションを開始**してください。有効化したプロジェクトは同じユーザーのグローバル習慣を共有し、各プロジェクトの記憶は分離されます。DeepSeek はローカル DSH を指し、Web・モバイルのチャットではインストーラーを実行できません。

**Codex はユーザー単位の有効化にも対応します。** 次を一度実行すると、プロジェクトごとの初期化なしでグローバル習慣を使えます。

```sh
npx -y --prefer-online chrisstarr7/dev-memory codex --user
```

ユーザー単位の対応は現在 Codex のみです。他のホストはプロジェクトのアダプターを使います。同じインストールコマンドで管理対象のプログラムを更新でき、記憶と無関係な指示は保持します。オフライン導入、ホストごとのパス、削除方法は [インストールガイド](../../docs/installation.md) を参照してください。

## 日常の使い方

設定後は通常どおり開発します。現在の AI が可視のユーザーフィードバックから習慣を抽出し、ローカルプログラムに保存します。バックグラウンドの会話監視や別の学習モデルはありません。

| 操作 | AI への依頼例 |
| --- | --- |
| 習慣を訂正する | 「この好みを修正して。既存実装は要件に合う場合だけ再利用して」 |
| 学習を一時停止する | 「グローバル習慣の書き込みを停止し、取得は続けて」 |
| 今回を除外する | 「このターンの記憶は保存しないで」 |
| 習慣を忘れる | 「削除範囲を表示し、確認後に削除して」 |

新規プロジェクトは **`developer-first`** が既定です。グローバル習慣を優先し、既存プロジェクト記録は取得できますが、新規業務記録・チェックポイントは追加しません。必要なら AI にインストール済み CLI を `full-project` へ切り替えるよう依頼してください。詳細は [インストールガイド](../../docs/installation.md) にあります。通常の開発は必要な記憶の取得と新しい反応の一括保存で進み、毎ターン全体のプロフィールを再構築しません。

## ローカル保存と管理

| 記憶 | 既定の場所 |
| --- | --- |
| グローバルな開発習慣 | `~/.dev-memory/global/` |
| 任意のプロジェクト規則・チェックポイント | `<project-root>/.dev-memory/` |

SQLite が個別の習慣、証拠、改訂を保存し、有効な習慣の集合が作業プロフィールになります。冪等な書き込み、分離、バックアップ、読み取り専用、確認付き削除に対応します。グローバルな信号は業務情報を取り除き、プロジェクト名、業務データ、コード、パス、元の会話を含めないでください。コアは記憶をアップロードせず、テレメトリーを収集しません。モデル処理にはホストのデータポリシーが適用されます。

## 資料と検証

実行時の依存は Python 標準ライブラリと SQLite です。プログラム、対話の意味、実ホストの評価を分けて記録しています。インストール成功は設定の確認であり、自動利用はホストの指示読み込みと AI の遵守に依存します。実際の Codex での二つのプロジェクトにまたがるユーザー指示の読み込み、および無効・旧版・新版の同一タスク性能比較は未検証です。

[構成](../../docs/architecture.md) · [プロトコル](../../skills/dev-memory/references/protocol.md) · [検証](../../reports/verification.md) · [0.7.0 タスク比較](../../reports/benchmark-0.7.0.md) · [安全性](../../SECURITY.md) · [貢献](../../CONTRIBUTING.md)

問題は機密情報を除いて [GitHub Issues](https://github.com/chrisstarr7/dev-memory/issues) に報告してください。[MIT License](../../LICENSE) で公開しています。
