# datlinx (DATa LIneage lyNX)

`CREATE PROCEDURE` / `CREATE FUNCTION` / `CREATE VIEW` のSQLファイルの `FROM/JOIN` を解析し、依存関係マップ（データリネージ・マインドマップ）の生成・検索を行うシングルファイル静的Webアプリケーションです。

---

## 🌟 主な機能

- **[1] SQLフォルダ・ファイル入力**:
  - `CREATE PROCEDURE` / `CREATE FUNCTION` / `CREATE VIEW` のDDLが書かれた `*.sql` ファイル群をまとめたフォルダを一括読み込み（`<input webkitdirectory>` およびドラッグ＆ドロップ対応）。
  - サンプルSQL (10件) をボタン一つで即座に読み込めるデモ機能内蔵。
- **[2] 依存関係マインドマップ自動描画**:
  - 指定された正規表現パターンに基づき、SQL内の `FROM` / `JOIN` 節から依存元のテーブル名・プロシージャ名・ビュー名を抽出。
  - 左側に「依存元（テーブル等）」、右側に向かって「依存先（ビューやプロシージャ）」を滑らかなベジェ曲線（矢印付き）で結ぶ階層的マインドマップを自動レイアウト。
  - ノード間に十分なマージン（水平・垂直）を取り、重なりのない美しい自動センタリング配置。
  - ノードは自由にドラッグ移動可能（接続線がリアルタイム追従）。
  - マウスホイールでのズーム、ドラッグによるパン移動、全体表示フィットボタンを完備。
- **[3] 検索フォーム（部分一致ハイライト）**:
  - テーブル名・プロシージャ名・ビュー名の一部を入力すると、該当ノードが薄い橙色背景にハイライトされ、キャンバスが該当ノードへスムーズにフォーカス。
- **[4] 依存関係の多方向洗い出し（3色ビジュアル分類）**:
  - マインドマップ上の任意の要素（テーブル/プロシージャ/ビュー）をクリックすると、一目でデータフローの系譜を洗い出せます。
    - **選択要素**: **薄い橙色背景**（オレンジ枠）
    - **依存元（上流の要素・親）**: **薄い緑色背景** ＆ **依存線・矢印が緑色**
    - **依存先（下流の要素・子）**: **薄い赤色背景** ＆ **依存線・矢印が赤色**
    - 関係のない要素は自動でディミング（半透明化）され、対象のデータリネージが鮮明に浮かび上がります。

---

## 🚀 クイックスタート

1. ブラウザ（Google Chrome, Edge 等）で `index.html` をダブルクリックして開きます。
2. 画面上部の **「📂 フォルダを開く」** から `sample` フォルダを選択するか、キャンバス中央の **「🧪 サンプルSQL (10件) で試す」** をクリックします。
3. 自動的に依存関係マインドマップが生成・描画されます。

---

## 📁 サンプルデータ (`sample/`)

本プロジェクトには、検証・動作確認用として `sample/` フォルダ内に10個のSQLファイルを用意しています。

| ファイル名 | 種別 | 依存元 (FROM / JOIN) |
| :--- | :--- | :--- |
| `v_active_users.sql` | VIEW | `m_users` |
| `v_order_details.sql` | VIEW | `dbo.t_orders`, `dbo.t_order_items`, `dbo.m_products` |
| `v_user_order_summary.sql` | VIEW | `v_active_users`, `v_order_details` |
| `v_low_stock_products.sql` | VIEW | `m_products`, `t_inventory` |
| `fn_get_user_discount.sql` | FUNCTION | `dbo.v_user_order_summary` |
| `sp_generate_monthly_sales_report.sql` | PROCEDURE | `dbo.v_order_details`, `dbo.v_user_order_summary` |
| `sp_refresh_daily_kpi.sql` | PROCEDURE | `v_active_users`, `v_user_order_summary` |
| `sp_inventory_alert.sql` | PROCEDURE | `v_low_stock_products` |
| `sp_customer_churn_analysis.sql` | PROCEDURE | `v_active_users`, `t_orders` |
| `sp_full_audit_process.sql` | PROCEDURE | `dbo.v_order_details`, `dbo.v_active_users`, `dbo.t_inventory` |

---

## 🔍 抽出正規表現

SQLファイル内の `FROM` / `JOIN` から参照先を抽出する正規表現パターン：

```regex
(FROM|JOIN)( ?
.*| )(
.*)?([a-zA-Z0-9]+\.)?(テーブル名|プロシージャ名|ビュー名)
```
