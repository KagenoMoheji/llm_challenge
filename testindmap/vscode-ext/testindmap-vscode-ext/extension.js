const vscode = require('vscode');
const path = require('path');
const fs = require('fs');

/**
 * 拡張機能のアクティベーション
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
    // カスタムエディタープロバイダーの登録
    const provider = new TestindmapEditorProvider(context);
    context.subscriptions.push(
        vscode.window.registerCustomEditorProvider(
            TestindmapEditorProvider.viewType,
            provider,
            {
                webviewOptions: {
                    retainContextWhenHidden: true,
                    enableScripts: true
                },
                supportsMultipleEditorsPerDocument: false
            }
        )
    );

    // 新規作成コマンド
    context.subscriptions.push(
        vscode.commands.registerCommand('testindmap.new', async () => {
            const workspaceFolders = vscode.workspace.workspaceFolders;
            let defaultUri;
            if (workspaceFolders && workspaceFolders.length > 0) {
                defaultUri = vscode.Uri.joinPath(workspaceFolders[0].uri, 'test_mindmap.testmap.json');
            } else {
                defaultUri = vscode.Uri.file('test_mindmap.testmap.json');
            }

            const targetUri = await vscode.window.showSaveDialog({
                defaultUri: defaultUri,
                filters: {
                    'Testindmap JSON (*.testmap.json)': ['testmap.json', 'json'],
                    'All Files': ['*']
                },
                saveLabel: '作成'
            });

            if (targetUri) {
                // 空のJSONテンプレートを作成
                const initialContent = JSON.stringify({
                    export_date: new Date().toISOString(),
                    version: '1.0',
                    nodes: []
                }, null, 2);

                await vscode.workspace.fs.writeFile(targetUri, Buffer.from(initialContent, 'utf8'));
                // 作成したファイルをカスタムエディタで開く
                await vscode.commands.executeCommand('vscode.openWith', targetUri, TestindmapEditorProvider.viewType);
            }
        })
    );

    // 既存ファイルを開くコマンド
    context.subscriptions.push(
        vscode.commands.registerCommand('testindmap.open', async () => {
            const uris = await vscode.window.showOpenDialog({
                canSelectFiles: true,
                canSelectFolders: false,
                canSelectMany: false,
                filters: {
                    'Testindmap Files (*.json, *.tsv)': ['json', 'tsv'],
                    'All Files': ['*']
                },
                openLabel: 'マインドマップで開く'
            });

            if (uris && uris.length > 0) {
                await vscode.commands.executeCommand('vscode.openWith', uris[0], TestindmapEditorProvider.viewType);
            }
        })
    );
}

/**
 * カスタムエディタープロバイダー
 */
class TestindmapEditorProvider {
    static viewType = 'testindmap.editor';

    constructor(context) {
        this.context = context;
    }

    /**
     * カスタムエディタの解決
     * @param {vscode.TextDocument} document
     * @param {vscode.WebviewPanel} webviewPanel
     * @param {vscode.CancellationToken} token
     */
    async resolveCustomTextEditor(document, webviewPanel, token) {
        const webview = webviewPanel.webview;

        // ローカルリソースへのアクセスを許可
        webview.options = {
            enableScripts: true,
            localResourceRoots: [
                vscode.Uri.joinPath(this.context.extensionUri, 'media')
            ]
        };

        // WebviewのHTMLをセット
        webview.html = this.getHtmlForWebview(webview);

        let isUpdatingFromWebview = false;

        // Webviewからのメッセージを受信
        const messageSubscription = webview.onDidReceiveMessage(async (message) => {
            switch (message.type) {
                case 'ready':
                    // Webview準備完了時に現在のドキュメント内容を送信
                    webview.postMessage({
                        type: 'load',
                        text: document.getText(),
                        fileName: path.basename(document.uri.fsPath)
                    });
                    break;

                case 'change':
                    // Webview側で変更があった場合、ドキュメントに反映
                    if (document.getText() !== message.text) {
                        isUpdatingFromWebview = true;
                        try {
                            await this.updateTextDocument(document, message.text);
                        } finally {
                            isUpdatingFromWebview = false;
                        }
                    }
                    break;

                case 'exportFile':
                    // ファイルエクスポート
                    try {
                        const ext = message.fileType === 'tsv' ? 'tsv' : 'json';
                        const filterName = message.fileType === 'tsv' ? 'TSV Files (*.tsv)' : 'JSON Files (*.json)';
                        const defaultUri = vscode.Uri.joinPath(
                            vscode.workspace.workspaceFolders?.[0]?.uri || vscode.Uri.file(''),
                            message.defaultName || `test_mindmap.${ext}`
                        );

                        const targetUri = await vscode.window.showSaveDialog({
                            defaultUri: defaultUri,
                            filters: {
                                [filterName]: [ext],
                                'All Files': ['*']
                            }
                        });

                        if (targetUri) {
                            await vscode.workspace.fs.writeFile(targetUri, Buffer.from(message.content, 'utf8'));
                            vscode.window.showInformationMessage(`エクスポートが完了しました: ${path.basename(targetUri.fsPath)}`);
                        }
                    } catch (err) {
                        vscode.window.showErrorMessage(`エクスポート中にエラーが発生しました: ${err.message}`);
                    }
                    break;

                case 'requestImport':
                    // ファイルインポート
                    try {
                        const uris = await vscode.window.showOpenDialog({
                            canSelectFiles: true,
                            canSelectFolders: false,
                            canSelectMany: false,
                            filters: {
                                'Testindmap Files (*.json, *.tsv)': ['json', 'tsv'],
                                'All Files': ['*']
                            },
                            openLabel: 'インポート'
                        });

                        if (uris && uris.length > 0) {
                            const fileBytes = await vscode.workspace.fs.readFile(uris[0]);
                            const fileText = Buffer.from(fileBytes).toString('utf8');
                            const fileName = path.basename(uris[0].fsPath).toLowerCase();
                            const format = fileName.endsWith('.tsv') ? 'tsv' : 'json';

                            webview.postMessage({
                                type: 'importedData',
                                text: fileText,
                                format: format
                            });

                            vscode.window.showInformationMessage(`インポートしました: ${path.basename(uris[0].fsPath)}`);
                        }
                    } catch (err) {
                        vscode.window.showErrorMessage(`インポート中にエラーが発生しました: ${err.message}`);
                    }
                    break;

                case 'confirmClear':
                    // すべてクリアの確認
                    {
                        const answer = await vscode.window.showWarningMessage(
                            '本当にすべてのノードを削除しますか？',
                            { modal: true },
                            'すべて削除'
                        );
                        if (answer === 'すべて削除') {
                            webview.postMessage({ type: 'doClear' });
                        }
                    }
                    break;

                case 'confirmDeleteNode':
                    // ノード削除の確認
                    {
                        const label = message.testCaseId ? `テストケース [${message.testCaseId}]` : '選択中のノード';
                        const answer = await vscode.window.showWarningMessage(
                            `本当に ${label} を削除しますか？`,
                            { modal: true },
                            '削除'
                        );
                        if (answer === '削除') {
                            webview.postMessage({ type: 'doDeleteNode', nodeId: message.nodeId });
                        }
                    }
                    break;

                case 'warning':
                    vscode.window.showWarningMessage(message.text);
                    break;

                case 'error':
                    vscode.window.showErrorMessage(message.text);
                    break;
            }
        });

        // ドキュメントが外部または元に戻す操作で変更された場合の監視
        const changeDocumentSubscription = vscode.workspace.onDidChangeTextDocument((e) => {
            if (e.document.uri.toString() === document.uri.toString()) {
                if (!isUpdatingFromWebview) {
                    webview.postMessage({
                        type: 'load',
                        text: document.getText(),
                        fileName: path.basename(document.uri.fsPath)
                    });
                }
            }
        });

        // パネルが破棄された時のクリーンアップ
        webviewPanel.onDidDispose(() => {
            messageSubscription.dispose();
            changeDocumentSubscription.dispose();
        });
    }

    /**
     * ドキュメント内容の全置換
     * @param {vscode.TextDocument} document
     * @param {string} newText
     */
    async updateTextDocument(document, newText) {
        const edit = new vscode.WorkspaceEdit();
        const fullRange = new vscode.Range(
            document.positionAt(0),
            document.positionAt(document.getText().length)
        );
        edit.replace(document.uri, fullRange, newText);
        return vscode.workspace.applyEdit(edit);
    }

    /**
     * Webview用HTMLの構築
     * @param {vscode.Webview} webview
     * @returns {string}
     */
    getHtmlForWebview(webview) {
        const mediaPath = vscode.Uri.joinPath(this.context.extensionUri, 'media');
        const templatePath = path.join(mediaPath.fsPath, 'app.html');
        let html = fs.readFileSync(templatePath, 'utf8');

        const monomdUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'monomd.js'));
        const appCssUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'app.css'));
        const appJsUri = webview.asWebviewUri(vscode.Uri.joinPath(mediaPath, 'app.js'));

        html = html.replace(/\{\{cspSource\}\}/g, webview.cspSource);
        html = html.replace(/\{\{monomdUri\}\}/g, monomdUri.toString());
        html = html.replace(/\{\{appCssUri\}\}/g, appCssUri.toString());
        html = html.replace(/\{\{appJsUri\}\}/g, appJsUri.toString());

        return html;
    }
}

function deactivate() {}

module.exports = {
    activate,
    deactivate
};
