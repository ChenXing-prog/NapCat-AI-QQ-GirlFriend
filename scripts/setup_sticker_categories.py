#!/usr/bin/env python3
"""Create 30 sticker category directories with meta.json files."""

import json
from pathlib import Path

STICKER_CATEGORIES = [
    # 喜悦系
    {"tag": "laugh", "label": "大笑", "use_when": "笑死、爆笑、太好笑了、笑不活了", "example": "哈哈哈哈哈哈"},
    {"tag": "smile", "label": "微笑", "use_when": "开心、温馨、心情好、你好呀", "example": "今天天气真好"},
    {"tag": "smirk", "label": "坏笑", "use_when": "嘿嘿嘿、有小九九、偷偷开心、计划通", "example": "嘿嘿～我想到个好主意"},
    {"tag": "star_eyes", "label": "星星眼", "use_when": "崇拜、好厉害、太牛了、 Amazing", "example": "哇！你也太强了吧！"},
    {"tag": "satisfied", "label": "满足", "use_when": "吃饱了、爽到了、圆满了、一本满足", "example": "好饱～满足了"},
    {"tag": "excited", "label": "兴奋", "use_when": "太好了、耶！！、太期待了、冲冲冲", "example": "终于要放假了！耶！"},
    # 撒娇系
    {"tag": "shy", "label": "害羞", "use_when": "被夸了、脸红、不好意思、扭捏", "example": "哪有你说的那样..."},
    {"tag": "cute", "label": "卖萌", "use_when": "求关注、可爱、撒娇、蹭蹭", "example": "陪我嘛～(｡･ω･｡)"},
    {"tag": "clingy", "label": "黏人", "use_when": "别走、陪陪我、不想分开、想你了", "example": "再多陪我一会儿嘛～"},
    {"tag": "begging", "label": "求求了", "use_when": "拜托拜托、跪求、求你了、行行好", "example": "求求你了嘛～"},
    {"tag": "pout", "label": "撅嘴", "use_when": "哼、不乐意、不高兴、赌气", "example": "哼，不理你了"},
    # 傲娇/无奈系
    {"tag": "tsundere", "label": "傲娇", "use_when": "才不是为你、口是心非、嘴硬心软、哼", "example": "才不是特意等你呢！"},
    {"tag": "eye_roll", "label": "嫌弃", "use_when": "翻白眼、无语、鄙视、受不了", "example": "你这人...（翻白眼）"},
    {"tag": "speechless", "label": "无语", "use_when": "不知道该说什么、沉默了、呆住", "example": "...（沉默）"},
    {"tag": "questioning", "label": "问号", "use_when": "？？？、黑人问号、啥？、一脸懵", "example": "什么鬼？？？"},
    {"tag": "sigh", "label": "叹气", "use_when": "唉、心累、叹气、又这样了", "example": "唉...又加班了"},
    # 关心系
    {"tag": "caring", "label": "关心", "use_when": "担心你、注意身体、好好休息、别太累了", "example": "记得多喝水哦"},
    {"tag": "pat", "label": "摸摸头", "use_when": "安慰、乖、摸摸头、好了好了", "example": "乖～摸摸头"},
    {"tag": "hug", "label": "抱抱", "use_when": "想要拥抱、贴贴、抱抱你、给你温暖", "example": "过来让我抱抱～"},
    {"tag": "love", "label": "比心", "use_when": "爱你、喜欢你、比心、心动", "example": "喜欢你～(｡･ω･｡)ﾉ♡"},
    # 难过系
    {"tag": "cry", "label": "大哭", "use_when": "呜呜呜、哭死、爆哭、泪崩", "example": "呜呜呜...太难了"},
    {"tag": "teary", "label": "委屈", "use_when": "被冤枉、好委屈、含泪、想哭", "example": "明明不是我的错..."},
    {"tag": "heartbroken", "label": "心碎", "use_when": "受伤了、心碎了、被背叛、好痛", "example": "你怎么能这样..."},
    {"tag": "corner", "label": "蹲角落", "use_when": "自闭了、别理我、面壁、不想说话", "example": "让我一个人静静..."},
    # 吃惊系
    {"tag": "shocked", "label": "震惊", "use_when": "什么！！、不会吧！！、惊呆了、震撼", "example": "什么！？真的假的！？"},
    {"tag": "panic", "label": "慌张", "use_when": "完了完了、来不及了、 panic、慌得一批", "example": "完了完了要迟到了！"},
    # 整活系
    {"tag": "peek", "label": "暗中观察", "use_when": "让我看看、暗中观察、偷偷看、窥屏", "example": "让我看看你在干嘛～"},
    {"tag": "proud", "label": "得意", "use_when": "哼我厉害吧、骄傲、求夸奖、得瑟", "example": "哼～我厉害吧(｀・ω・´)"},
    {"tag": "sleepy", "label": "困了", "use_when": "晚安、好困、想睡觉、打哈欠", "example": "好困...先睡了哦"},
    {"tag": "rage", "label": "暴怒", "use_when": "掀桌！、气炸了、 fury、怒气冲天", "example": "气死我了！！！"},
]


def main():
    root = Path(__file__).parent.parent / "stickers"
    root.mkdir(exist_ok=True)

    for cat in STICKER_CATEGORIES:
        tag = cat["tag"]
        folder = root / tag
        folder.mkdir(exist_ok=True)

        meta = {
            "emotion": tag,
            "label": cat["label"],
            "use_when": cat["use_when"],
            "example": cat["example"],
        }
        meta_file = folder / "meta.json"
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"✅ {tag:12s} → {cat['label']} ({meta_file})")

    print(f"\n共创建 {len(STICKER_CATEGORIES)} 个分类目录")
    print(f"根目录: {root}")


if __name__ == "__main__":
    main()
