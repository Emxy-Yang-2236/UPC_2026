# 维护与发布

本仓库保存可分发 skill 的完整源码。研究题目、原始论文、求解结果与个人配置请保存在仓库之外。`README.md` 是面向使用者的唯一安装与使用说明。

## 首次上传已准备的版本

本地目录已初始化为 Git 仓库。首次上传前可运行 `git status`、`git log -1 --oneline` 和 `git tag --list` 查看提交与版本标签。在 GitHub 创建一个空的公开仓库，名称建议 `upc-physics`；不用额外生成 README、LICENSE 或 `.gitignore`，这些文件已在本地提供。

在本目录打开终端，将 `REPOSITORY_URL` 换成你新建仓库的 HTTPS 地址，执行：

```text
git remote add origin REPOSITORY_URL
git push -u origin main
git push origin v0.2.0
```

如果已有 `origin`，先用 `git remote -v` 核对地址再操作。认证使用你自己的 GitHub 登录方式。

在 GitHub 的 Releases 页面创建 `v0.2.0` Release，选择刚上传的同名标签，标题填写 `UPC Physics v0.2.0`。正文可使用本地 `.github/release-notes-v0.2.0.md`，附件从 `dist/v0.2.0/` 选择以下四个文件：

- `upc-physics-v0.2.0.zip`
- `upc-physics-v0.2.0.skill`
- `manifest.json`
- `SHA256SUMS`

`dist/` 已被 Git 忽略，因此通过 Release 附件上传，无需提交生成包。若上传前修改了 skill 或说明文件，请先重新测试、打包并提交，再确保版本标签指向该提交；上面步骤假设使用已准备的版本。

## 修改

1. 在本仓库修改需要维护的模块、参考文件或工具；核对来源和结论适用范围。
2. 更新 `VERSION`、`CHANGELOG.md` 和 README 中的版本及下载文件名。新增随包文件时同步修改 `release-files.txt`。
3. 运行现有工具回归与发布检查：

```text
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tools/build_release.py --output dist/candidate
```

构建只读取清单中的普通文件，拒绝符号链接、越界路径、缺失文件及断开的包内文档链接。ZIP 固定顺序、时间戳、权限并使用无压缩存储，因此相同输入在不同主机上生成相同字节。`.skill` 是同一 ZIP 的另一个文件扩展名。`manifest.json` 记录文件及包的 SHA-256，`SHA256SUMS` 还覆盖清单本身。

若输出目录中已有内容不同的发布文件，构建会停止；改用新的输出目录，核对后保留需要的版本。发布后的版本及附件应保持稳定，更改内容时增加版本号。

## GitHub 发布

在完整源码仓库中使用 Git 与已登录的 GitHub CLI。先核对 `git diff`、测试结果和 `git status`，仅提交预期文件。下面的命令以 `v0.2.0` 为例；后续发布需替换版本、路径和发布说明文件。

```text
git push origin main
git tag -a v0.2.0 -m "UPC Physics v0.2.0"
git push origin v0.2.0
gh release create v0.2.0 dist/candidate/upc-physics-v0.2.0.zip dist/candidate/upc-physics-v0.2.0.skill dist/candidate/manifest.json dist/candidate/SHA256SUMS --verify-tag --title "UPC Physics v0.2.0" --notes-file .github/release-notes-v0.2.0.md
```

发布前应已有包含当前版本的提交；标签必须指向通过检查的提交。首次准备的本地 `v0.2.0` 标签已存在时直接推送即可，不重复创建。仓库 CI 会运行 Python 工具测试和构建；基础 MATLAB 检查需在具备软件与许可的机器另行运行。CI 不替代物理建模审查。

## 贡献

欢迎提交具体的错误复现、模型检查改进、可移植性修复或写作流程改进。案例反馈应提炼可迁移的方法，保留事实、假设和推断的边界；不要在改进 skill 时混入某个练习的完整解答或无权分发的原始材料。

贡献者须有权提交所提供的内容，并接受本仓库原创部分采用的 [MIT 许可](LICENSE)。采用第三方代码或文字时，应单独核对兼容性、保留所需许可与署名，并更新 [来源说明](NOTICE.md)。
