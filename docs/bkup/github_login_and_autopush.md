# GitHub ログイン設定 & Claude Code 自動push

---

## 1. GitHubへのログイン方法

### A. HTTPS（トークン方式）

#### トークンの取得

1. GitHub → 右上アイコン → **Settings**
2. 左メニュー一番下 → **Developer settings**
3. **Personal access tokens** からトークン種別を選ぶ

**① Tokens (classic) の場合**
- **Generate new token** をクリック
- 権限は `repo` にチェックを入れて生成

**② Fine-grained tokens の場合**
- **Generate new token** をクリック
- リポジトリの範囲：**All repositories**（またはNayuStampのみ）
- 「**+ Add permissions**」から以下を設定：

| 権限 | 設定値 |
|------|--------|
| **Contents** | **Read and write** |
| **Metadata** | Read-only（自動でオンになる） |

4. 表示されたトークンをコピー（一度しか表示されないので注意）

#### ローカルに設定
```bash
git config --global user.name ike0904
git config --global user.email ike0904@gmail.com
```

初回pushの際にパスワードを聞かれたら、トークンを貼り付けます。

#### トークンを毎回入力しないようにする
```bash
git config --global credential.helper store
```
一度入力すれば次回から自動でログインされます。

---

### B. SSH鍵方式

#### SSH鍵を生成
```bash
ssh-keygen -t ed25519 -C "メールアドレス"
```
そのままEnterを3回押せばOK。

#### 公開鍵をGitHubに登録
```bash
# 公開鍵の内容を表示
cat ~/.ssh/id_ed25519.pub
```
表示された内容をコピーして：

1. GitHub → **Settings** → **SSH and GPG keys**
2. **New SSH key** をクリック
3. コピーした内容を貼り付けて保存

#### 接続確認
```bash
ssh -T git@github.com
# "Hi ユーザー名!" と表示されればOK
```

#### リモートURLをSSHに変更
```bash
git remote set-url origin git@github.com:ユーザー名/NayuStamp.git
```

---

## 2. Claude Code から自動pushする方法

### CLAUDE.md に指示を書く

プロジェクトの `CLAUDE.md`（なければ新規作成）に以下を追記：

```markdown
## Git運用ルール

作業完了後は必ず以下を実行すること：
1. 変更内容を確認する（git status）
2. 全ファイルをステージング（git add .）
3. 変更内容を簡潔に説明したメッセージでコミット
4. GitHubにpushする（git push）
```

### Claude Codeへの指示例

作業を依頼するときにこう伝えます：

```
〇〇を修正して。完了したらgit commit & pushまでやって。
```

または `CLAUDE.md` にルールを書いておけば、毎回言わなくても自動でpushしてくれます。

---

## 3. よく使うgitコマンド早見表

| コマンド | 意味 |
|----------|------|
| `git status` | 変更状況を確認 |
| `git add .` | 全変更をステージング |
| `git commit -m "メモ"` | コミット |
| `git push` | GitHubに反映 |
| `git pull` | GitHubから最新を取得 |
| `git log --oneline` | コミット履歴を確認 |
