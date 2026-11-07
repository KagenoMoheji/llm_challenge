const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

/**
 * 拡張機能のアクティベーション
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    let currentPanel = null;
    let currentFolderPath = null;
    let currentFilesData = [];

    // WebviewPanelの作成または表示
    function getOrCreateWebviewPanel() {
        if (currentPanel) {
            currentPanel.reveal(vscode.ViewColumn.One);
            return currentPanel;
        }

        const mediaPath = vscode.Uri.joinPath(context.extensionUri, 'media');

        currentPanel = vscode.window.createWebviewPanel(
            'datlinxMindmap',
            'datlinx: SQL Lineage Mindmap',
            vscode.ViewColumn.One,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
                localResourceRoots: [mediaPath]
            }
        );

        currentPanel.iconPath = {
            light: vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.svg')),
            dark: vscode.Uri.file(path.join(context.extensionPath, 'media', 'icon.svg'))
        };

        const webview = currentPanel.webview;
        webview.html = getHtmlForWebview(webview, context);

        // Webviewからのメッセージハンドリング
        webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'ready':
                    // Webview準備完了時に最新データを送信
                    if (currentFilesData && currentFilesData.length > 0) {
                        sendDataToWebview(webview, currentFilesData, currentFolderPath);
                    } else {
                        // データがまだなければサンプルを自動表示
                        loadSampleData(webview);
                    }
                    break;

                case 'selectFolder':
                    // Webview内のボタンからフォルダ選択ダイアログを起動
                    await promptAndOpenFolder();
                    break;

                case 'openFileInEditor':
                    // ノードからVS Codeエディタでファイルを開く
                    if (message.filePath) {
                        try {
                            const uri = vscode.Uri.file(message.filePath);
                            const doc = await vscode.workspace.openTextDocument(uri);
                            await vscode.window.showTextDocument(doc, { viewColumn: vscode.ViewColumn.Beside });
                        } catch (err) {
                            vscode.window.showErrorMessage(`ファイルを開けませんでした: ${err.message}`);
                        }
                    }
                    break;

                case 'reload':
                    // 現在のフォルダを再走査
                    if (currentFolderPath) {
                        await loadFolder(currentFolderPath);
                    } else {
                        loadSampleData(webview);
                    }
                    break;
            }
        }, undefined, context.subscriptions);

        currentPanel.onDidDispose(() => {
            currentPanel = null;
        }, undefined, context.subscriptions);

        return currentPanel;
    }

    // Webviewへデータ送信
    function sendDataToWebview(webview, filesData, folderName) {
        webview.postMessage({
            type: 'loadFiles',
            folderName: folderName ? path.basename(folderName) : 'Sample Data',
            folderPath: folderName || '',
            files: filesData
        });
    }

    // フォルダ再帰探索で .sql ファイルを収集
    async function scanSqlFiles(dirPath, fileList = []) {
        const entries = await fs.promises.readdir(dirPath, { withFileTypes: true });
        for (const entry of entries) {
            const fullPath = path.join(dirPath, entry.name);
            if (entry.isDirectory()) {
                // node_modulesや.gitは除外
                if (entry.name !== 'node_modules' && entry.name !== '.git') {
                    await scanSqlFiles(fullPath, fileList);
                }
            } else if (entry.isFile() && entry.name.toLowerCase().endsWith('.sql')) {
                const content = await fs.promises.readFile(fullPath, 'utf8');
                fileList.push({
                    name: entry.name,
                    fullPath: fullPath,
                    content: content
                });
            }
        }
        return fileList;
    }

    // 指定フォルダを読み込んで表示
    async function loadFolder(targetPath) {
        try {
            vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: "datlinx: SQLファイルを解析中...",
                cancellable: false
            }, async () => {
                const files = await scanSqlFiles(targetPath);
                if (files.length === 0) {
                    vscode.window.showWarningMessage(`指定フォルダ内に .sql ファイルが見つかりませんでした: ${targetPath}`);
                    return;
                }

                currentFolderPath = targetPath;
                currentFilesData = files;

                const panel = getOrCreateWebviewPanel();
                panel.title = `datlinx: ${path.basename(targetPath)}`;
                sendDataToWebview(panel.webview, files, targetPath);
            });
        } catch (err) {
            vscode.window.showErrorMessage(`SQLファイルの読み込みに失敗しました: ${err.message}`);
        }
    }

    // フォルダ選択プロンプト
    async function promptAndOpenFolder(initialUri) {
        const uris = await vscode.window.showOpenDialog({
            defaultUri: initialUri,
            canSelectFiles: false,
            canSelectFolders: true,
            canSelectMany: false,
            openLabel: 'マインドマップで解析'
        });

        if (uris && uris.length > 0) {
            await loadFolder(uris[0].fsPath);
        }
    }

    // サンプルデータを読み込み
    function loadSampleData(webview) {
        const sampleFiles = getSampleSqlList();
        currentFolderPath = null;
        currentFilesData = sampleFiles;
        sendDataToWebview(webview, sampleFiles, 'Sample Data (10 files)');
    }

    // 1. コマンド: フォルダを開く (エクスプローラー右クリック / パレット)
    context.subscriptions.push(
        vscode.commands.registerCommand('datlinx.openFolder', async (uri) => {
            if (uri && uri.fsPath) {
                // エクスプローラーでフォルダを右クリックした場合
                await loadFolder(uri.fsPath);
            } else {
                // コマンドパレットからの場合
                const workspaceFolders = vscode.workspace.workspaceFolders;
                const defaultUri = workspaceFolders && workspaceFolders.length > 0 ? workspaceFolders[0].uri : undefined;
                await promptAndOpenFolder(defaultUri);
            }
        })
    );

    // 2. コマンド: ワークスペース全体を解析
    context.subscriptions.push(
        vscode.commands.registerCommand('datlinx.openWorkspace', async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (!workspaceFolders || workspaceFolders.length === 0) {
                vscode.window.showWarningMessage('開かれているワークスペースがありません。');
                return;
            }
            await loadFolder(workspaceFolders[0].uri.fsPath);
        })
    );

    // 3. コマンド: サンプルで開く
    context.subscriptions.push(
        vscode.commands.registerCommand('datlinx.openSample', () => {
            const panel = getOrCreateWebviewPanel();
            panel.title = 'datlinx: サンプルデータ';
            loadSampleData(panel.webview);
        })
    );
}

/**
 * Webview HTMLの生成
 */
function getHtmlForWebview(webview, context) {
    const mediaPath = vscode.Uri.joinPath(context.extensionUri, 'media');
    const templatePath = path.join(mediaPath.fsPath, 'app.html');
    let html = fs.readFileSync(templatePath, 'utf8');

    const appCssUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'app.css'));
    const appJsUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'app.js'));

    html = html.replace(/\{\{cspSource\}\}/g, webview.cspSource);
    html = html.replace(/\{\{appCssUri\}\}/g, appCssUri.toString());
    html = html.replace(/\{\{appJsUri\}\}/g, appJsUri.toString());

    return html;
}

/**
 * 内蔵サンプルSQLリスト (10ファイル)
 */
function getSampleSqlList() {
    return [
        {
            name: "v_active_users.sql",
            fullPath: "",
            content: `CREATE VIEW v_active_users AS
SELECT
    user_id,
    user_name,
    email,
    created_at
FROM m_users
WHERE status = 'ACTIVE'
  AND is_deleted = 0;`
        },
        {
            name: "v_order_details.sql",
            fullPath: "",
            content: `CREATE VIEW dbo.v_order_details AS
SELECT
    o.order_id,
    o.user_id,
    o.order_date,
    oi.product_id,
    p.product_name,
    oi.quantity,
    oi.unit_price,
    (oi.quantity * oi.unit_price) AS subtotal
FROM
    dbo.t_orders o
INNER JOIN dbo.t_order_items oi
    ON o.order_id = oi.order_id
LEFT JOIN
    dbo.m_products p
    ON oi.product_id = p.product_id;`
        },
        {
            name: "v_user_order_summary.sql",
            fullPath: "",
            content: `CREATE VIEW v_user_order_summary AS
SELECT
    u.user_id,
    u.user_name,
    COUNT(d.order_id) AS total_orders,
    SUM(d.subtotal) AS total_spent
FROM v_active_users u
LEFT JOIN v_order_details d
    ON u.user_id = d.user_id
GROUP BY
    u.user_id,
    u.user_name;`
        },
        {
            name: "v_low_stock_products.sql",
            fullPath: "",
            content: `CREATE VIEW v_low_stock_products AS
SELECT
    p.product_id,
    p.product_name,
    i.current_stock,
    i.safety_stock
FROM
    m_products p
JOIN
    t_inventory i
    ON p.product_id = i.product_id
WHERE
    i.current_stock < i.safety_stock;`
        },
        {
            name: "fn_get_user_discount.sql",
            fullPath: "",
            content: `CREATE FUNCTION dbo.fn_get_user_discount (
    @user_id INT
)
RETURNS DECIMAL(5, 2)
AS
BEGIN
    DECLARE @discount DECIMAL(5, 2) = 0.00;

    SELECT
        @discount = CASE
            WHEN total_spent > 100000 THEN 0.15
            WHEN total_spent > 50000  THEN 0.10
            ELSE 0.05
        END
    FROM dbo.v_user_order_summary
    WHERE user_id = @user_id;

    RETURN @discount;
END;`
        },
        {
            name: "sp_generate_monthly_sales_report.sql",
            fullPath: "",
            content: `CREATE PROCEDURE dbo.sp_generate_monthly_sales_report
    @target_year INT,
    @target_month INT
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        d.product_id,
        d.product_name,
        COUNT(d.order_id) AS monthly_order_count,
        SUM(d.subtotal) AS total_monthly_sales
    FROM
        dbo.v_order_details d
    INNER JOIN
        dbo.v_user_order_summary s
        ON d.user_id = s.user_id
    WHERE
        YEAR(d.order_date) = @target_year
        AND MONTH(d.order_date) = @target_month
    GROUP BY
        d.product_id,
        d.product_name;
END;`
        },
        {
            name: "sp_refresh_daily_kpi.sql",
            fullPath: "",
            content: `CREATE PROCEDURE sp_refresh_daily_kpi
AS
BEGIN
    SET NOCOUNT ON;

    -- Daily KPI calculation from user order summary and active users
    SELECT
        CAST(GETDATE() AS DATE) AS calculation_date,
        COUNT(DISTINCT u.user_id) AS active_user_count,
        SUM(s.total_spent) AS daily_turnover
    FROM v_active_users u
    JOIN v_user_order_summary s
        ON u.user_id = s.user_id;
END;`
        },
        {
            name: "sp_inventory_alert.sql",
            fullPath: "",
            content: `CREATE PROCEDURE sp_inventory_alert
AS
BEGIN
    SET NOCOUNT ON;

    -- Extract low stock products needing immediate reorder
    SELECT
        product_id,
        product_name,
        current_stock,
        safety_stock,
        (safety_stock - current_stock) AS reorder_quantity
    FROM
        v_low_stock_products
    WHERE current_stock <= safety_stock;
END;`
        },
        {
            name: "sp_customer_churn_analysis.sql",
            fullPath: "",
            content: `CREATE PROCEDURE sp_customer_churn_analysis
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        u.user_id,
        u.user_name,
        MAX(o.order_date) AS last_order_date,
        DATEDIFF(day, MAX(o.order_date), GETDATE()) AS days_since_last_order
    FROM v_active_users u
    LEFT JOIN t_orders o
        ON u.user_id = o.user_id
    GROUP BY
        u.user_id,
        u.user_name
    HAVING
        DATEDIFF(day, MAX(o.order_date), GETDATE()) > 90;
END;`
        },
        {
            name: "sp_full_audit_process.sql",
            fullPath: "",
            content: `CREATE PROCEDURE dbo.sp_full_audit_process
AS
BEGIN
    SET NOCOUNT ON;

    -- Full audit joining order details, users, and inventory
    SELECT
        d.order_id,
        d.product_name,
        d.quantity,
        i.current_stock,
        u.user_name
    FROM
        dbo.v_order_details d
    INNER JOIN
        dbo.v_active_users u
        ON d.user_id = u.user_id
    INNER JOIN
        dbo.t_inventory i
        ON d.product_id = i.product_id;
END;`
        }
    ];
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
