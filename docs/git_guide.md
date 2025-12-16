# Git 版本控制使用指南（单人开发）

本文档针对**单人开发**场景，提供简单实用的 Git 使用指南。

## 一、Git 基础概念

### 什么是 Git？

Git 是一个**分布式版本控制系统**，可以：
- 📝 记录代码的每次修改历史
- 🔄 可以随时回退到之前的版本
- 🌿 支持分支开发，不影响主代码
- 📦 备份代码到远程仓库（如 GitHub）

### 核心概念

```
工作区 (Working Directory)
    ↓ git add
暂存区 (Staging Area)
    ↓ git commit
本地仓库 (Local Repository)
    ↓ git push
远程仓库 (Remote Repository)
```

## 二、首次设置 Git

### 1. 安装 Git

**macOS**:
```bash
# 如果已安装 Homebrew
brew install git

# 或从官网下载
# https://git-scm.com/download/mac
```

**检查安装**:
```bash
git --version
```

### 2. 配置个人信息（只需做一次）

```bash
# 设置用户名（可以是你喜欢的任何名字）
git config --global user.name "Your Name"

# 设置邮箱
git config --global user.email "your.email@example.com"

# 查看配置
git config --list
```

### 3. 初始化仓库

在你的项目目录下：
```bash
cd /Users/100buy/项目重构/FindQC_Refactor_v2
git init
```

## 三、日常开发工作流（推荐流程）

### 基本流程（3步走）

```bash
# 1. 查看当前状态
git status

# 2. 添加要提交的文件（可以多次 add）
git add 文件名           # 添加单个文件
git add 目录/            # 添加整个目录
git add .               # 添加所有修改的文件

# 3. 提交更改（写清楚本次改了什么）
git commit -m "描述你做了什么"
```

### 实际例子

假设你刚刚创建了 `shared_lib/models.py`:

```bash
# 1. 看看有哪些文件被修改了
git status

# 2. 添加新文件
git add shared_lib/models.py

# 或者添加所有修改
git add .

# 3. 提交（写清楚做了什么）
git commit -m "添加数据库模型定义：商品表和任务表"
```

### 查看提交历史

```bash
# 查看所有提交记录
git log

# 简洁版（一行显示）
git log --oneline

# 查看最近5条
git log -5 --oneline
```

### 查看文件差异

```bash
# 查看工作区和暂存区的差异
git diff

# 查看某个文件的具体修改
git diff 文件名
```

## 四、提交信息规范（推荐）

好的提交信息能帮助你快速了解代码变更历史：

```
格式：类型: 简短描述

类型：
- feat: 新功能
- fix: 修复bug
- docs: 文档更新
- style: 代码格式调整（不影响功能）
- refactor: 代码重构
- test: 测试相关
- chore: 构建/工具相关

例子：
git commit -m "feat: 实现商品爬虫服务的基础框架"
git commit -m "fix: 修复数据库连接池配置错误"
git commit -m "docs: 更新 API 接口文档"
git commit -m "refactor: 重构 AI 处理流程，提高可维护性"
```

## 五、常用命令速查

### 查看状态

```bash
git status              # 查看工作区状态
git log                 # 查看提交历史
git log --oneline       # 简洁版历史
git diff                # 查看未暂存的修改
```

### 提交更改

```bash
git add .               # 添加所有修改
git add 文件/目录        # 添加指定文件/目录
git commit -m "描述"    # 提交更改
```

### 撤销操作（谨慎使用）

```bash
# 撤销工作区的修改（危险！会丢失未提交的修改）
git checkout -- 文件名

# 撤销暂存区的文件（保留工作区修改）
git reset HEAD 文件名

# 撤销最后一次提交（保留修改）
git reset --soft HEAD^
```

### 忽略文件

不需要提交的文件写在 `.gitignore` 中，例如：
- 虚拟环境 (`venv/`)
- Python 缓存 (`__pycache__/`)
- 配置文件 (`.env`)
- 日志文件 (`*.log`)

## 六、远程仓库（可选但推荐）

### 为什么需要远程仓库？

- 💾 代码备份（本地硬盘坏了也不怕）
- 🌐 多设备同步（家里和公司都能访问）
- 📤 展示项目（可以分享给他人）

### 创建 GitHub 仓库

1. 登录 GitHub (https://github.com)
2. 点击右上角 "+" → "New repository"
3. 输入仓库名称（如 `FindQC_Refactor_v2`）
4. 选择 Public 或 Private
5. **不要**勾选 "Initialize with README"（因为本地已有）
6. 点击 "Create repository"

### 连接远程仓库

```bash
# 添加远程仓库（只需要做一次）
git remote add origin https://github.com/你的用户名/FindQC_Refactor_v2.git

# 查看远程仓库
git remote -v

# 首次推送（把所有本地代码推送到远程）
git branch -M main              # 设置主分支名为 main
git push -u origin main         # 推送并设置上游分支
```

### 后续推送代码

```bash
# 推送本地提交到远程
git push

# 如果提示需要先拉取远程更新
git pull    # 先拉取
git push    # 再推送
```

## 七、单人开发最佳实践

### 1. 频繁提交，少量多次

```bash
# ✅ 好的习惯：完成一个小功能就提交
git add .
git commit -m "feat: 添加商品爬取的基础函数"
git commit -m "feat: 添加数据库连接配置"
git commit -m "fix: 修复图片 URL 解析错误"

# ❌ 不好的习惯：一天只提交一次，包含很多不相关的修改
```

### 2. 提交前检查

```bash
# 提交前先看看改了啥
git status
git diff

# 确认无误后再提交
git add .
git commit -m "描述"
```

### 3. 重要的里程碑打标签

```bash
# 完成一个重要版本后打标签
git tag -a v1.0.0 -m "第一个可用版本"
git push origin v1.0.0
```

### 4. 定期推送备份

```bash
# 每天下班前推送一次，确保代码安全
git push
```

## 八、常见场景处理

### 场景1：忘记提交，直接修改了代码

```bash
# 先提交之前的修改
git add .
git commit -m "之前的修改"

# 然后再继续开发
```

### 场景2：提交信息写错了

```bash
# 修改最后一次提交信息
git commit --amend -m "正确的提交信息"
```

### 场景3：想回退到之前的版本

```bash
# 查看提交历史，找到要回退的版本号
git log --oneline

# 回退到指定版本（保留工作区修改）
git reset --soft 版本号

# 完全回退（危险！会丢失修改）
git reset --hard 版本号
```

### 场景4：误删了文件

```bash
# 从 Git 恢复文件
git checkout -- 文件名
```

## 九、推荐工具

- **命令行**: Git 自带（本文档主要介绍）
- **图形界面**: 
  - GitHub Desktop (https://desktop.github.com)
  - Sourcetree (https://www.sourcetreeapp.com)
  - VS Code 内置 Git 支持

## 十、学习资源

- **官方文档**: https://git-scm.com/doc
- **交互式教程**: https://learngitbranching.js.org/
- **GitHub 帮助**: https://docs.github.com/

---

**提示**: 作为单人开发者，掌握以上命令就足够了。遇到问题随时查文档或搜索引擎，Git 社区很活跃，大部分问题都有解决方案。

