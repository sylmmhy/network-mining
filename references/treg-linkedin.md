# TREG 和 LinkedIn 数据：接口、价格、局限

TREG（https://treg.to）是第三方社媒数据服务，Eazo Creator 的社交搜索也在用它。

## 怎么调

- **查目录**：免费，不要钥匙。
  - `GET https://treg.to/catalog/search?q=linkedin&limit=20`
  - `GET https://treg.to/catalog/endpoints/{id}`：返回价格、参数、调用模板。
  - 用新接口前先查目录，确认参数和价格。
- **实际调用**：`GET https://treg.to/call/{id}?<参数>`，请求头带 `X-Treg-Token: <TREG_API_KEY>`。
  - 每次花了多少钱看响应头 `x-treg-cost-micro`，单位是百万分之一美元。脚本会累计并打印。
- **钥匙**：属于公司团队账户，由用户每次在对话里给。不写进文件、记忆或 skill。

## 用到的接口（2026-11 实测）

| 接口 | 参数 | 返回 | 约价 |
| --- | --- | --- | --- |
| `harvestapi.linkedin.user.posts` | `profile`=主页链接，`postedLimit=month`，`page`，`paginationToken`，`scrapePostedLimit` | 每页最多 50 条帖子，带日期、互动数、作者信息（`author.info` 是自我介绍） | 每页 $0.002 |
| `harvestapi.linkedin.user.comments` | `profile`，`postedLimit`，`page`，`paginationToken` | 本人写的评论，含所在帖子和帖子作者 | 每页约 $0.004 |
| `harvestapi.linkedin.post.comments` | `post`=帖子链接，`sortBy=date` | 帖子下的一级留言（第一页最多 50 条，最新的在前），带留言人职位、回复数 | 每次约 $0.004 |
| `harvestapi.linkedin.user.reactions` | `profile` | 本人点过的赞 | 约 $0.004（没用过） |
| `treg.linkedin.user.profile` | 主页 | 个人资料（可能有关注者数，没验证过字段） | 用前查目录 |

2026-11-16 至 17 的实际花费：1,509 人筛选，加上 6 人深挖、9 人浅挖、21 人深挖，一共约 4.9 美元。

## 拿不到的

- **没有"我的联系人名单"接口。** LinkedIn 官方接口只能查自己的资料和发帖，联系人名单只能让用户导出 Connections.csv。
- **私信看不到。** 所以结论只能说到"公开处没看到"。
- **评论楼中楼的内容看不到。** 一级留言只给"下面有几条回复"，看不到是谁回的、回了什么。要确认是不是本人回的，得在本人的评论数据里找那条回复（链接里带 `replyUrn`，`commentUrn` 里那串数字就是被回复的留言）。

## 数据的坑

- **Connections.csv 的格式**：开头有一段 "Notes:" 说明，真正的表头从 `First Name,Last Name,URL,...` 那一行开始。约 2% 的人没有主页链接。
- **日期字段**：评论的日期用 `createdAt`。`postedAt` 是原帖的时间，用错会把所有评论都算成近期。
- **`postedLimit=month` 不严格**，会多给，日期要自己过滤。
- **判断是不是转发**：`header.text` 里含 "reposted"，或者作者的 `publicIdentifier` 不是本人，就是转发。
- **每页最多 50 条。** 筛选时评论只抓一页，活跃评论者会被严重少算（例：名单上记 32 条，深挖实际一个月 163 条）。热门帖留言也只抓到最新 50 条，几百条留言的帖子，早期留言会缺。
- **帖子 ID 能换算发帖时间**：`activity-<19位数字>` 右移 22 位，得到毫秒时间戳。
- **`publicIdentifier` 可能为空**（公司主页等），代码里要防空。
- **"留言领资料"的引流帖**会让收到的留言数虚高，所以来往分里留言最多计 50。是不是引流号要深挖确认。例：有两个人看着像引流号，深挖后发现是一群人互相评论。
- **导出包里还有私信、求职记录等文件**，只解出 Connections.csv。
