# network-mining：人脉逐人挖掘

一个 Claude Code skill。它从你的 LinkedIn 联系人里找出活跃的人，读他们的公开帖子和评论，逐人写出两件事：

- 这个人是谁、为什么这么做、为什么回谁不回谁；
- 一个 AI 助手能为他做什么、第一句话该说什么。

每条结论都带证据链接，方便人工核对。

核心方法是**先懂人，再想能做什么**：画像 → 动机 → 用动机解释行为 → 最后才提建议。详见 `references/method.md`。

## 安装

```bash
git clone https://github.com/sylmmhy/network-mining.git ~/.claude/skills/network-mining
```

装好后，在 Claude Code 里说"深挖某某""帮我挖 LinkedIn 联系人""分析一下这个人的动机"之类的话，就会用到它。

## 需要准备

- **数据服务**：[TREG](https://treg.to) 的 API 钥匙，运行时通过环境变量 `TREG_API_KEY` 临时传入。**仓库里不存任何钥匙。**
- **联系人名单**：从 LinkedIn 导出数据（设置 → 数据隐私 → 获取数据副本 → Connections），只用其中的 `Connections.csv`。
- **运行环境**：Python 3，只用标准库。

## 目录

| 文件 | 用途 |
| --- | --- |
| `SKILL.md` | 完整流程：拿名单 → 筛选 → 排名 → 深挖 → 动机统计 → 写作 → 核对 → 交付 |
| `references/method.md` | 先懂人再想能做什么：方法、检查项、自查清单 |
| `references/writing-brief.md` | 单人章节的写作说明和模板 |
| `references/treg-linkedin.md` | TREG 接口、价格、数据局限 |
| `scripts/screen.py` | 全量筛选联系人（可中断续跑） |
| `scripts/rank.py` | 按"来往分"排出优先级名单 |
| `scripts/deep.py` | 深挖抓取 |
| `scripts/motive_stats.py` | 动机分析用的行为统计（不联网） |
| `scripts/verify_links.py` | 核对成品里的链接是否都来自原始数据 |

## 隐私

- 只用公开数据，不发帖、不私信、不关注、不点赞。
- 抓下来的数据和成品报告含第三方信息，不放进这个仓库，`.gitignore` 已经排除。
- 带真实人物的成品样例（`references/example-private.md`）只存在本地。
