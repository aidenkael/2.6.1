"""最小关键词引擎（从 keyword_tool v4.2 稳定方向库提取的纯数据副本）。

只保留：分类（cn/en 大类词）+ 每个分类下的具体中英文搜索词。
不包含联网扩词、诊断、代理、CSV、日志等 keyword_tool 其他能力。
原目录 keyword_tool 保持只读，本模块不依赖其运行时。
"""

from __future__ import annotations

import random

# 每个分类: {"cn": 分类中文名, "en": 英文大类词, "items": [(中文词, 英文词), ...]}
DIRECTIONS = [{'cn': '女性家居桌面美化', 'en': 'home and desk decor', 'items': [('蕾丝床头防尘罩', 'lace headboard cover french style'), ('亚克力波浪桌面镜', 'wavy acrylic desk mirror'), ('硅胶花瓣杯垫', 'silicone floral cup coaster'), ('簇绒几何枕套', 'tufted boho pillow cover'), ('编织太阳花壁挂', 'macrame sunflower wall hanging'), ('法式复古蕾丝桌布', 'vintage lace tablecloth'), ('书本造型储物盒', 'book shaped storage box'), ('桌面迷你垃圾桶', 'mini desktop trash can'), ('布艺开关贴', 'fabric light switch cover sticker'), ('治愈系床头摆件', 'healing bedside table decor')]}, {'cn': '现代收纳整理', 'en': 'storage and organization', 'items': [('蜂窝抽屉分隔板', 'honeycomb drawer organizer divider'), ('布艺发夹挂墙袋', 'wall hanging hair accessory organizer'), ('折叠太阳镜挂袋', 'folding sunglasses organizer case'), ('衣柜包包收纳挂袋', 'purse organizer for closet hanging'), ('PU皮理线器', 'leather cable strap organizer'), ('帆布大容量化妆笔袋', 'large capacity canvas cosmetic pencil case'), ('水杯侧边悬挂收纳包', 'water bottle side pouch'), ('内衣旅行收纳盒', 'lingerie travel organizer'), ('鞋子收纳袋', 'shoe storage bags'), ('桌面笔筒收纳', 'desk pen holder organizer')]}, {'cn': '包包与女性随身周边', 'en': 'bag and carry accessories', 'items': [('芭蕾风蝴蝶结包挂', 'coquette bow bag charm'), ('珍珠手机斜挎链', 'pearl phone strap lanyard'), ('润唇膏钥匙圈挂件', 'lip balm holder keychain neoprene'), ('包包收纳挂钩', 'bag hanger hook'), ('丝巾包带', 'scarf bag wrap'), ('包包防尘袋', 'dust bag for handbags'), ('包包内胆包', 'handbag organizer insert'), ('包包肩带垫', 'bag strap shoulder pad'), ('腕带钥匙扣卡包', 'keychain card holder wallet wristlet'), ('帽子收纳夹', 'hat storage clip')]}, {'cn': '数码非电子配件', 'en': 'non electronic tech accessories', 'items': [('毛绒笔记本内胆包', 'cute embroidered laptop sleeve'), ('硅胶耳机装饰猫耳', 'silicone cat ears attachment for headphones'), ('毛线无线耳机壳', 'crochet wireless earbuds case cover'), ('水钻伸缩证件扣', 'cute rhinestone retractable badge reel'), ('懒人手机指环支架', 'lazy phone holder ring finger plastic'), ('数据线收纳夹', 'cable organizer clips'), ('电脑包收纳袋', 'laptop sleeve pouch'), ('键盘清洁刷', 'keyboard cleaning brush'), ('桌面理线夹', 'desktop cable clips'), ('手机挂绳垫片', 'phone lanyard patch connector')]}, {'cn': '创意厨房小工具', 'en': 'creative kitchen gadgets', 'items': [('龙头防溅水托盘', 'silicone sink faucet splash guard'), ('硅胶锅盖防溢垫', 'silicone pot lid lifter spill stopper'), ('动物造型封口夹', 'cute animal chip clips'), ('烤箱防烫隔热手夹', 'mini silicone oven mitts'), ('手动塑料压蒜盒', 'manual plastic garlic twister crusher'), ('塑料水果去核工具', 'cherry pitter tool plastic'), ('塑料牛油果切片器', 'plastic avocado slicer pitter'), ('硅胶甜甜圈模具', 'silicone donut baking mold'), ('树叶水槽过滤网', 'leaf shape silicone sink strainer'), ('欧式刺绣餐垫', 'embroidered floral table placemat')]}, {'cn': '食品保鲜与封口工具', 'en': 'food storage and sealing tools', 'items': [('食品封口夹', 'food bag sealing clips'), ('硅胶食物保鲜盖', 'silicone food saver lid'), ('水果保鲜硅胶盖', 'fruit food huggers silicone lid'), ('调料袋封口夹', 'spice bag sealing clips'), ('宠物食品封口夹', 'pet food sealing clip'), ('冰箱分区标签夹', 'fridge label clips'), ('密封袋整理架', 'food storage bag organizer'), ('保鲜膜切割盒非刀片款', 'plastic wrap dispenser safe cutter'), ('硅胶碗盖套装', 'silicone bowl covers set'), ('面包袋封口扣', 'bread bag clips')]}, {'cn': '女性健康轻健身', 'en': 'fitness and wellness accessories', 'items': [('乳胶圈健身带', 'booty resistance bands latex'), ('无绳跳绳负重球', 'ropeless jump rope cordless weighted ball'), ('束腰带高弹力', 'waist trainer belt sweat wrap'), ('超细纤维瑜伽铺巾', 'microfiber yoga mat towel non slip'), ('洗脸防流汗护腕', 'wrist sweatbands for face washing'), ('硅胶足弓支撑带', 'arch support sleeve silicone'), ('EVA瑜伽砖', 'high density EVA yoga block'), ('硅胶手指拉力器', 'silicone finger gripper resistance trainer'), ('高弹手机跑步腰包', 'slim running belt phone fanny pack'), ('跑步防滑发圈', 'non slip sports headband')]}, {'cn': '轻医疗边缘运动辅助', 'en': 'light support and recovery accessories', 'items': [('运动护膝套', 'knee support sleeve for workout'), ('运动护腕套', 'wrist support sleeve for fitness'), ('运动护踝套', 'ankle support sleeve for workout'), ('足弓支撑硅胶带', 'arch support sleeve silicone'), ('瑜伽拉伸带', 'yoga stretching strap'), ('按摩滚轮棒', 'massage roller stick for fitness'), ('弹力绳门锚', 'resistance band door anchor'), ('手指拉力器', 'finger gripper resistance trainer'), ('运动护肩带', 'shoulder support strap workout'), ('健身器材收纳袋', 'gym accessory storage pouch')]}, {'cn': '节日季节性装饰', 'en': 'seasonal and holiday decor', 'items': [('万圣节桌旗', 'halloween table runner'), ('圣诞餐刀叉口袋', 'christmas silverware holder pockets'), ('复活节毛毡挂件', 'easter felt bunny hanging ornaments'), ('感恩节枫叶挂饰', 'thanksgiving maple leaf banner'), ('生日派对雨丝帘', 'metallic tinsel fringe curtain party'), ('新年纸眼镜', 'happy new year paper glasses party favors'), ('情人节酒瓶装饰套', 'valentines day wine bottle cover'), ('毕业季派对桌牌', 'graduation party table sign'), ('独立日大蝴蝶结头饰', '4th of july hair bow'), ('婚礼花瓣装饰', 'wedding confetti petals')]}, {'cn': '玩具边缘成人解压摆件', 'en': 'adult stress relief desk accessories', 'items': [('慢回弹猫爪解压摆件', 'slow rising cat paw stress relief'), ('指尖减压旋转器', 'fidget spinner desk accessory'), ('办公室解压球', 'office stress relief ball'), ('ASMR桌面小物', 'ASMR desk sensory accessory'), ('毛绒情绪挂件', 'mood plush keychain'), ('正能量针织小摆件', 'positive crochet desk gift'), ('趣味桌面减压摆件', 'funny desk stress relief ornament'), ('硅胶按压解压垫', 'silicone fidget desk pad'), ('木鱼禅意钥匙扣', 'mini wooden fish zen keychain'), ('治愈系桌面小摆件', 'cute healing desk ornament')]}, {'cn': '宠物轻便周边', 'en': 'pet travel and accessories', 'items': [('宠物毛发清理刷', 'pet hair remover brush'), ('狗狗口水巾', 'dog bandana summer pattern'), ('硅胶折叠宠物碗', 'collapsible silicone dog bowl travel'), ('宠物垃圾袋挂包', 'dog poop bag holder dispenser'), ('宠物防舔软脖圈', 'soft cat recovery collar'), ('宠物洗澡防抓脚套', 'silicone cat anti scratch boots'), ('狗狗夏日防晒帽', 'dog baseball cap with ear holes'), ('宠物牵引绳收纳袋', 'pet leash storage pouch'), ('宠物碗垫', 'pet bowl mat'), ('宠物便携水杯袋', 'pet travel bottle pouch')]}, {'cn': '低风险美妆美甲发饰周边', 'en': 'beauty accessories and nail art', 'items': [('塑料假睫毛夹', 'plastic false eyelashes applicator tool'), ('亚克力睫毛收纳盒', 'acrylic false eyelash storage case'), ('穿戴甲片果冻胶贴', 'press on nails jelly glue tabs'), ('美甲贴纸', 'nail art stickers'), ('硅胶美甲练习手指', 'silicone practice finger for nail art'), ('丝绒大肠发圈', 'oversized velvet scrunchies'), ('莫兰迪色鲨鱼夹', 'large matte claw clips'), ('洗脸吸水头套', 'spa headband for washing face plush'), ('化妆海绵晾晒架', 'silicone makeup sponge holder'), ('丝绸懒人卷发棒', 'heatless hair curler satin')]}, {'cn': '旅行收纳用品', 'en': 'travel organizer accessories', 'items': [('旅行收纳包', 'travel packing cubes'), ('旅行鞋袋', 'travel shoe bag'), ('护照证件收纳包', 'passport document organizer pouch'), ('行李箱束带', 'luggage strap'), ('创意硅胶行李牌', 'cute silicone luggage tag'), ('旅行洗漱包', 'toiletry bag'), ('化妆刷收纳包', 'makeup brush organizer bag'), ('旅行内衣收纳袋', 'underwear travel organizer'), ('旅行脏衣袋', 'travel laundry bag'), ('旅行瓶收纳袋', 'travel bottle storage pouch')]}, {'cn': '鞋类周边低尺码风险', 'en': 'shoe accessories low size risk', 'items': [('洞洞鞋鞋花', 'clog shoe charms'), ('蝴蝶结鞋扣', 'bow shoe clips'), ('珍珠鞋扣装饰', 'pearl shoe clip accessories'), ('弹力免系鞋带', 'elastic no tie shoelaces'), ('鞋带装饰扣', 'shoelace charm clips'), ('旅行鞋袋', 'travel shoe bags'), ('鞋盒分类标签', 'shoe box labels tags'), ('防磨后跟贴', 'heel cushion pads'), ('高跟鞋防滑贴', 'shoe anti slip pads'), ('鞋类收纳挂袋', 'hanging shoe organizer bag')]}, {'cn': '汽车内饰小物', 'en': 'car interior accessories', 'items': [('汽车座椅挂钩', 'car seat hook'), ('汽车杯垫', 'car cup holder coaster'), ('安全带护肩套', 'seat belt shoulder pad'), ('汽车遮阳板收纳夹', 'car sun visor organizer'), ('汽车纸巾盒套', 'car tissue box cover'), ('汽车门边防撞贴', 'car door edge protector'), ('汽车后备箱收纳网', 'car trunk storage net'), ('车载手机置物袋', 'car phone storage pouch'), ('汽车钥匙包', 'car key pouch'), ('车内仪表台摆件', 'car dashboard decor')]}, {'cn': '户外轻用品', 'en': 'light outdoor accessories', 'items': [('防晒袖套', 'sun protection arm sleeves'), ('运动冰巾', 'cooling sports towel'), ('便携水杯袋', 'portable bottle pouch'), ('野餐收纳袋', 'picnic storage pouch'), ('帽子防风夹', 'hat windproof clip'), ('沙滩包收纳袋', 'beach bag organizer'), ('户外挂钩', 'outdoor hanging hook'), ('露营餐具收纳袋', 'camping cutlery storage pouch'), ('棒球帽眼镜固定扣', 'sunglasses holder clip for hat cap'), ('挂脖水杯托', 'cup sleeve with shoulder strap')]}, {'cn': '浴室生活小物', 'en': 'bathroom life accessories', 'items': [('硅藻土肥皂托盘', 'diatomite soap dish'), ('挤牙膏器', 'toothpaste squeezer'), ('浴室防水手机架', 'waterproof shower phone holder'), ('浴室挂钩', 'bathroom adhesive hooks'), ('硅藻泥吸水垫', 'diatomite absorbent mat'), ('洗脸防湿袖护腕', 'face washing wristbands'), ('牙刷杯收纳架', 'toothbrush cup holder'), ('浴室台面收纳盒', 'bathroom countertop organizer'), ('毛巾固定夹', 'towel holder clip'), ('淋浴用品收纳袋', 'shower caddy pouch')]}, {'cn': '办公桌面小物', 'en': 'office desk accessories', 'items': [('桌面文件收纳盒', 'desktop file organizer'), ('便利贴收纳盒', 'sticky note holder'), ('桌面杯垫', 'desk coaster'), ('书签夹', 'bookmark clips'), ('亚克力名言摆件', 'acrylic inspirational quote sign'), ('3D立体便签纸', '3d sticky note cube'), ('鼠标护腕垫', 'mouse wrist rest pad'), ('办公室桌面装饰牌', 'office desk sign decor'), ('桌面小花瓶', 'mini desktop vase'), ('桌面收纳托盘', 'desktop organizer tray')]}, {'cn': '大学宿舍公寓装饰', 'en': 'college dorm and apartment decor', 'items': [('北欧风墙壁挂毯', 'boho wall tapestry'), ('毛绒坐垫', 'fluffy seat cushion'), ('毛绒床边地毯', 'fluffy bedside rug'), ('蕾丝床头防尘罩', 'lace headboard cover'), ('宿舍桌面收纳盒', 'dorm desk organizer'), ('可爱眼镜盒', 'cute glasses case'), ('床边收纳袋', 'bedside hanging storage bag'), ('寝室门牌装饰', 'dorm room door sign decor'), ('墙面照片夹不带灯', 'photo wall clips no lights'), ('小型洗漱收纳篮', 'portable shower caddy basket')]}, {'cn': '派对拍照道具', 'en': 'party photo props', 'items': [('派对拍照道具', 'party photo booth props'), ('生日派对桌牌', 'birthday party table sign'), ('派对彩带', 'party ribbon streamers'), ('镭射雨丝帘', 'foil fringe curtain party backdrop'), ('礼品包装丝带', 'gift wrapping ribbon'), ('新年纸眼镜', 'new year paper glasses'), ('毕业季拍照道具', 'graduation photo props'), ('婚礼桌卡', 'wedding table place cards'), ('情人节礼品袋', 'valentines gift bag'), ('母亲节礼品盒', 'mothers day gift box')]}, {'cn': '通用风格女性小物', 'en': 'trend style women accessories', 'items': [('coquette蝴蝶结小物', 'coquette bow accessory'), ('balletcore丝带装饰', 'balletcore ribbon accessory'), ('y2k透明收纳小物', 'y2k transparent organizer'), ('kawaii桌面装饰', 'kawaii desk decor'), ('vintage复古收纳盒', 'vintage storage box'), ('minimalist极简包挂', 'minimalist bag charm'), ('boho编织装饰', 'boho woven decor'), ('aesthetic房间装饰', 'aesthetic room decor'), ('法式蕾丝小物', 'french lace accessory'), ('轻奢珍珠风配件', 'pearl style accessory')]}, {'cn': '礼品包装与套装化小物', 'en': 'gift packaging and bundle accessories', 'items': [('折叠礼品盒', 'foldable gift box'), ('礼品包装丝带', 'gift wrapping ribbon'), ('节日礼品袋', 'holiday gift bags'), ('透明礼品包装袋', 'clear gift packaging bags'), ('小卡片留言牌', 'gift message cards'), ('礼品贴纸封口贴', 'gift sealing stickers'), ('婚礼伴手礼袋', 'wedding favor bags'), ('生日礼品吊牌', 'birthday gift tags'), ('母亲节礼品盒', 'mothers day gift box'), ('香包外袋空袋', 'sachet pouch empty bag')]}]

EXPLORE_PREFIX = "【大类探索】"


# ── 中文→英文映射表（含大类探索） ────────────────────────────

def _build_cn_to_en() -> dict[str, str]:
    """构建中文→英文映射表（含大类探索）。"""
    mapping: dict[str, str] = {}
    for d in DIRECTIONS:
        mapping[EXPLORE_PREFIX + d["cn"]] = d["en"]
        for cn_word, en_word in d["items"]:
            if cn_word and en_word:
                mapping[cn_word] = en_word
    return mapping


_CN_TO_EN: dict[str, str] = _build_cn_to_en()


def resolve_cn_keyword(text: str) -> tuple[str, str]:
    """将单个中文搜索词解析为 (显示文本, 实际英文搜索词)。

    匹配内置词库返回 (中文词, 英文词)；
    未匹配返回 (自定义词, 自定义词)——原词搜索。
    """
    text = (text or "").strip()
    if not text:
        return ("", "")
    if text in _CN_TO_EN:
        return (text, _CN_TO_EN[text])
    if text.startswith(EXPLORE_PREFIX):
        cat_cn = text[len(EXPLORE_PREFIX):]
        en = category_en_word(cat_cn)
        if en:
            return (text, en)
    return (text, text)


def resolve_keywords_batch(text: str) -> list[tuple[str, str]]:
    """批量解析中文搜索词（按 ``；`` 分隔）。

    返回有序 [(下框显示文本, 实际执行搜索词), ...]。
    内置词：显示=英文词，实际=英文词。
    自定义：显示="—（原词搜索）"，实际=用户原始文本。
    """
    if not text or not text.strip():
        return []
    result: list[tuple[str, str]] = []
    for part in text.split("；"):
        part = part.strip()
        if not part:
            continue
        _cn_display, actual = resolve_cn_keyword(part)
        if actual == part and part not in _CN_TO_EN:
            show = "—（原词搜索）"
        else:
            show = actual
        result.append((show, actual))
    return result


def list_categories() -> list[str]:
    """返回全部稳定分类名（中文）。"""
    return [d["cn"] for d in DIRECTIONS]


def category_en_word(category: str) -> str:
    """返回分类的英文大类词；未知分类返回空串。"""
    for d in DIRECTIONS:
        if d["cn"] == category:
            return d["en"]
    return ""


def category_terms(category: str) -> list[tuple[str, str]]:
    """返回分类搜索词列表 [(显示文本, 实际搜索词), ...]。

    第一项固定为 ``【大类探索】<英文大类词>``，其后为具体英文搜索词。
    """
    en = category_en_word(category)
    terms: list[tuple[str, str]] = []
    if en:
        terms.append((EXPLORE_PREFIX + en, en))
    for d in DIRECTIONS:
        if d["cn"] != category:
            continue
        for _cn_word, en_word in d["items"]:
            if en_word:
                terms.append((en_word, en_word))
        break
    return terms


def category_cn_terms(category: str) -> list[tuple[str, str]]:
    """返回分类搜索词列表 [(中文显示, 实际英文搜索词), ...]。

    专供新 UI 多搜索词弹窗使用：第一项为 ``【大类探索】<中文分类名>``，
    其后为具体中文搜索词。具体中文词的实际英文值统一取自全局
    ``_CN_TO_EN`` canonical 映射——同一中文词在多分类英文略有差异时，
    全局映射作为唯一结果，保证弹窗选择、手工输入、英文预览与实际采集
    解析到同一个英文搜索词。不改变 ``category_terms()`` 的旧语义。
    """
    en = category_en_word(category)
    terms: list[tuple[str, str]] = []
    if en:
        terms.append((EXPLORE_PREFIX + category, en))
    for d in DIRECTIONS:
        if d["cn"] != category:
            continue
        for cn_word, en_word in d["items"]:
            if not (cn_word and en_word):
                continue
            terms.append((cn_word, _CN_TO_EN.get(cn_word, en_word)))
        break
    return terms


def resolve_search_keyword(text: str) -> str:
    """把下拉框文本解析成实际搜索词。

    命中 ``【大类探索】`` 前缀则返回英文大类词；
    其他情况视为用户自定义输入，原样返回。
    """
    text = (text or "").strip()
    if text.startswith(EXPLORE_PREFIX):
        return text[len(EXPLORE_PREFIX):].strip()
    return text


def random_idea(rng: random.Random | None = None) -> tuple[str, str]:
    """随机灵感：随机选一个分类和其中一个具体搜索词（不含大类探索）。

    返回 (分类名, 搜索词显示文本)。不联网。
    """
    r = rng or random
    pool = [d for d in DIRECTIONS if d["items"]]
    d = r.choice(pool)
    _cn_word, en_word = r.choice(d["items"])
    return d["cn"], en_word
