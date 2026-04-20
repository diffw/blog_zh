# SEO Migration Audit

## Snapshot

- WordPress pages found: `3`
- WordPress pages mapped to current Hugo routes: `2`
- WordPress attachment pages found: `110`
- WordPress attachment pages mapped to parent posts: `94`
- Attachment pages still unresolved: `16`

## WordPress Page Routes

- `?page_id=1371` -> `/about/`
- `?page_id=1375` -> `/links/`

## Unmapped Pages

- `?page_id=1728` `Idea` (`slug: idea`) has no Hugo route yet.

## Attachment Notes

- Attachment file types in export: `{'jpg': 62, 'png': 29, 'gif': 12, 'jpeg': 7}`
- Mapped attachment pages redirect to the parent post rather than to missing old media pages.

### Unresolved Attachment Pages

- `?attachment_id=6` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2019/04/tumblr_nw8agknvPm1s8rww1o1_500.jpg`
- `?attachment_id=1006` parent=`1004` file=`https://diff.im/blog/wp-content/uploads/2020/04/personal-website-from-2002-7see.png`
- `?attachment_id=1007` parent=`1004` file=`https://diff.im/blog/wp-content/uploads/2020/04/personal-website-from-2002-babymo-07.gif`
- `?attachment_id=1008` parent=`1004` file=`https://diff.im/blog/wp-content/uploads/2020/04/personal-website-from-2002-none-w.gif`
- `?attachment_id=1009` parent=`1004` file=`https://diff.im/blog/wp-content/uploads/2020/04/MissPanda.gif`
- `?attachment_id=1044` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2020/07/IMG_3568.jpg`
- `?attachment_id=1045` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2020/07/Fk5BVAWM3_OGoD8Io02XjLFDWZbG.jpglarge-copy.jpg`
- `?attachment_id=1046` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2020/07/26375681_1703070033048348_7009019849749823488_n.jpg`
- `?attachment_id=1047` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2020/07/59b889c147534cd091ad13c064610488.jpeg`
- `?attachment_id=1048` parent=`0` file=`https://diff.im/blog/wp-content/uploads/2020/07/640x640_e38e17a949bedcdfcb9ac315c1ff984daffc0827.jpg`
- ... and `6` more unresolved attachment pages.

## Hardcoded Legacy Links In Content

- `wangwangwang`: `9` matches across `5` files
  - `content/posts/GTD学习中....md` x2: `http://www.wangwangwang.org/i/?p=325`, `http://www.wangwangwang.org/i/wp-content/uploads/2009/07/igoogle.gif`
  - `content/posts/Hulitu-Dark.md` x1: `http://www.wangwangwang.org/i/?page_id=151`
  - `content/posts/再见，杭州.md` x1: `http://www.wangwangwang.org/i/?p=44`
  - `content/posts/狐狸兔.md` x4: `http://www.wangwangwang.org/wallpaper/hulitu0530/hulitu-1024-768.jpg`, `http://www.wangwangwang.org/wallpaper/hulitu0530/hulitu-1280-800.jpg`, `http://www.wangwangwang.org/wallpaper/hulitu0530/hulitu-1280-1024.jpg`
  - `content/posts/结婚啦！.md` x1: `http://www.wangwangwang.org/i/?p=132`
- `handhard`: `5` matches across `5` files
  - `content/posts/Berry&Cherry.md` x1: `http://www.handhard.com/blog/wp-content/uploads/2011/06/BC.png`
  - `content/posts/Dior.md` x1: `http://www.handhard.com/blog/wp-content/uploads/2010/12/62cc0776tw6dby9uj83xwj.png`
  - `content/posts/Stamped.md` x1: `http://handhard.com/blog/wp-content/uploads/2011/11/Screen-shot-2011-11-30-at-%E4%B8%8B%E5%8D%8812.10.22.png`
  - `content/posts/工作台.md` x1: `http://www.handhard.com/blog/wp-content/uploads/2011/02/IMG_6512.jpg`
  - `content/posts/近照.md` x1: `http://handhard.com/blog/wp-content/uploads/2011/11/diff@linleduo_2011.11.03.jpg`
- `wp_uploads`: `94` matches across `33` files
  - `content/posts/2007.md` x22: `http://diff.im/blog/wp-content/uploads/2008/01/qhum0s2p.jpg`, `http://diff.im/blog/wp-content/uploads/2008/01/j9env0dl.jpg`, `http://diff.im/blog/wp-content/uploads/2008/01/x0q4nt1w.jpg`
  - `content/posts/2020.03.26 - 节奏.md` x1: `http://diff.im/blog/wp-content/uploads/2020/03/monster.gif`
  - `content/posts/2020.03.29 - 图形设计是真爱（之一）.md` x2: `http://diff.im/blog/wp-content/uploads/2020/03/b03feet.jpg`, `http://diff.im/blog/wp-content/uploads/2020/03/negative-space-art-noma-bar-1.jpg`
  - `content/posts/2U发布.md` x1: `http://diff.im/blog/wp-content/uploads/2009/09/2U_3.png`
  - `content/posts/《秦制两千年 - 封建帝王的权力规则》简评.md` x1: `https://diff.im/blog/wp-content/uploads/2022/03/img_1345.png`
  - ... and `28` more files

## Recommended Next Actions

- Add server-side `301/308` redirects for `?p=ID`, `?page_id=ID`, and the mapped `?attachment_id=ID` URLs at the edge layer if Linode or Cloudflare is still available.
- Restore the missing `wp-content/uploads` tree under the Hugo site or move those images into the repository and rewrite post bodies to the new asset URLs.
- Review the unresolved `Idea` page and decide whether it needs a Hugo destination or a deliberate `410`/redirect strategy.
- Use Google Search Console to resubmit the sitemap and inspect a sample of old `?p=ID` URLs after the server-side redirects are in place.
