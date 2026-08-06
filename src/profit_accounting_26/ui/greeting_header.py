"""
双语随机问候栏 —— 三组件结构版。

布局：
  [Hi]  [蓝色背景用户名]  [中英双行问候]  …[未保存] [↻]

职责：
1. 内置 288 条中英双语问候语（加载时去除 “Hi 用户，” / “Hi User,” 前缀）；
2. 使用设置中已有的"显示名称"（1-8 个 Unicode 可见字符，空时回退"用户"）；
3. 软件本次启动时随机显示一条；
4. 点击刷新按钮随机切换，且尽量不连续重复；
5. 用户名改变后背景框内容与中英文问候立即刷新。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
import json
import random

from PySide6.QtCore import QObject, QSize, Qt, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QLabel, QPushButton

from profit_accounting_26.shared.paths import resource_path


# ------------------------------------------------------------------
# 构建时去除问候语中的 "Hi 用户，" / "Hi User," 前缀
# ------------------------------------------------------------------

def _strip_zh_prefix(zh: str) -> str:
    """去除中文问候语开头的 'Hi 用户，'。"""
    for prefix in ("Hi 用户，", "Hi 用户,"):
        if zh.startswith(prefix):
            return zh[len(prefix):]
    return zh


def _strip_en_prefix(en: str) -> str:
    """去除英文问候语开头的 'Hi User,' 以及紧随的空白。"""
    for prefix in ("Hi User, ", "Hi User,"):
        if en.startswith(prefix):
            return en[len(prefix):]
    return en


_GREETINGS_JSON = r"""[{"zh": "愿你今天遇到的都是小惊喜，绕开的都是小麻烦。", "en": "may today bring you small surprises and help you sidestep small troubles."}, {"zh": "愿你的早餐有温度，工作有进展，回家有放松。", "en": "may your breakfast be warm, your work move forward, and your evening feel restful."}, {"zh": "新的一天已经打开，愿你用喜欢的方式慢慢填写。", "en": "a new day is open—may you fill it in at your own pace."}, {"zh": "别忘了给认真生活的自己留一句表扬。", "en": "remember to leave a word of praise for the version of you who keeps showing up."}, {"zh": "愿今天的风轻一点，事情顺一点，心情亮一点。", "en": "may the breeze be gentle, your tasks go smoothly, and your mood feel brighter."}, {"zh": "希望你忙得有价值，也闲得心安理得。", "en": "may your busy moments feel worthwhile and your quiet moments feel well deserved."}, {"zh": "愿你今天有好消息，也有好胃口。", "en": "may you receive good news and enjoy a good appetite today."}, {"zh": "生活不必时时精彩，舒服自在也很好。", "en": "life does not need to be exciting every moment; feeling at ease is already good."}, {"zh": "愿你今天做的每件小事，都在悄悄靠近理想生活。", "en": "may every small thing you do today quietly move you toward the life you want."}, {"zh": "给今天留一点期待，也给自己留一点余地。", "en": "save a little anticipation for today and a little breathing room for yourself."}, {"zh": "愿你的认真被看见，努力有回应，疲惫有安放。", "en": "may your care be noticed, your effort be answered, and your tiredness find rest."}, {"zh": "今天也请把自己放在重要的位置。", "en": "please keep yourself on today’s list of important things."}, {"zh": "愿你打开软件时有思路，关掉软件时有收获。", "en": "may you open this app with ideas and close it with something gained."}, {"zh": "愿你今天少一点内耗，多一点真实的快乐。", "en": "may today bring less overthinking and more genuine joy."}, {"zh": "别急着赶路，先确认方向，也照顾好心情。", "en": "do not rush ahead—check your direction and take care of your mood."}, {"zh": "愿普通的一天也有值得记住的小片段。", "en": "may an ordinary day still contain a moment worth remembering."}, {"zh": "今天的你不必完美，真诚、清醒、向前就好。", "en": "you do not need to be perfect today—being sincere, clear-minded, and moving forward is enough."}, {"zh": "愿你手里有事做，心里有盼头，身边有温暖。", "en": "may your hands have meaningful work, your heart have hope, and your surroundings have warmth."}, {"zh": "愿今天的付出，在未来某天成为轻松的底气。", "en": "may today’s effort become tomorrow’s quiet confidence."}, {"zh": "世界很大，先把眼前这一小步走稳。", "en": "the world is wide; start by taking this next small step steadily."}, {"zh": "今天的目标很简单：订单多一点，麻烦少一点。", "en": "today’s goal is simple: more orders and fewer problems."}, {"zh": "愿你的客户看得懂详情，也看得懂你的良苦用心。", "en": "may customers understand both the product page and your good intentions."}, {"zh": "今天先把事情做完，再研究怎样显得毫不费力。", "en": "finish the work first, then figure out how to make it look effortless."}, {"zh": "愿你的保存按钮永远有效，撤销按钮永远来得及。", "en": "may the save button always work and the undo button always arrive in time."}, {"zh": "别怕事情多，一件一件做，它们总会失去气势。", "en": "do not fear a long task list; handle it one item at a time until it loses confidence."}, {"zh": "愿今天所有临时任务都懂礼貌，办完就走。", "en": "may every temporary task be polite enough to leave once completed."}, {"zh": "工作可以认真，表情不必一直像在处理国际危机。", "en": "take work seriously, but your face need not resemble an international crisis."}, {"zh": "今天先别追求奇迹，正常顺利已经很值得庆祝。", "en": "do not chase miracles today; ordinary smoothness is worth celebrating."}, {"zh": "愿你的沟通一次说清，别让同一句话往返包邮。", "en": "may one clear message be enough, with no free-return shipping for the same sentence."}, {"zh": "忙可以，别忙到忘了自己为什么忙。", "en": "being busy is fine; forgetting why you are busy is less ideal."}, {"zh": "愿你的计划不临时变脸，结果不突然失联。", "en": "may your plan avoid sudden personality changes and your results stay reachable."}, {"zh": "今天的困难看起来很嚣张，但它还没见过你列清单。", "en": "today’s difficulty looks confident, but it has not seen your checklist."}, {"zh": "愿你的消息提示少一点，成交提示多一点。", "en": "may there be fewer random notifications and more sales notifications."}, {"zh": "别急着全都做好，先把最重要的做好看。", "en": "do not perfect everything at once; make the most important part work well first."}, {"zh": "愿你今天少返工，多返现。", "en": "may you redo less work and receive more cashback today."}, {"zh": "工作不会辜负认真，只是有时回信比较慢。", "en": "work rarely ignores sincerity; it just replies slowly sometimes."}, {"zh": "今天先解决问题，情绪可以稍后排队处理。", "en": "solve the problem first; emotions may wait in the next queue."}, {"zh": "愿你的努力都能看见结果，不要只看见新任务。", "en": "may your effort produce visible results instead of merely revealing new tasks."}, {"zh": "今天适合稳稳推进，不适合和细节互相伤害。", "en": "today favors steady progress, not mutual destruction with tiny details."}, {"zh": "别怕进度慢，至少不是原地忙得很有气氛。", "en": "slow progress is fine; at least you are not standing still with great enthusiasm."}, {"zh": "愿你的表格整整齐齐，心情不要像表格一样被框住。", "en": "may your spreadsheets stay neat while your mood remains free of boxes."}, {"zh": "事情再复杂，也别把午饭当成可选功能。", "en": "however complex the day gets, lunch is not an optional feature."}, {"zh": "愿你今天处理的是订单，不是别人的情绪订单。", "en": "may you process real orders today, not everyone else’s emotional orders."}, {"zh": "今天不求惊艳全场，先求别被琐事包围。", "en": "no need to amaze everyone today; first avoid being surrounded by trivialities."}, {"zh": "先完成一件事，再奖励自己认真研究吃什么。", "en": "finish one task, then reward yourself by seriously deciding what to eat."}, {"zh": "午饭不是逃避工作，是给下午续费。", "en": "lunch is not avoiding work; it is renewing your afternoon subscription."}, {"zh": "今天的效率秘诀：吃饱、坐稳、少看群聊。", "en": "today’s productivity formula: eat well, sit steadily, and check fewer group chats."}, {"zh": "累了就休息，老板还没给你安装备用电池。", "en": "rest when tired; nobody has installed a spare battery in you."}, {"zh": "困不是你的错，是床的营销做得太成功。", "en": "sleepiness is not your fault; your bed simply has excellent marketing."}, {"zh": "愿你的下午茶及时出现，像救援队一样专业。", "en": "may afternoon tea arrive with the professionalism of a rescue team."}, {"zh": "工作可以晚点想，吃什么必须提前规划。", "en": "work can be considered later; food requires advance planning."}, {"zh": "先别焦虑，确认一下是不是只是饿了。", "en": "pause the anxiety and check whether you are simply hungry."}, {"zh": "今天可以摸鱼，但最好摸到一点灵感。", "en": "you may take a break today, but try to catch some inspiration while you are there."}, {"zh": "午休不是暂停人生，是给下半场加载资源。", "en": "a lunch break is not pausing life; it is loading resources for the second half."}, {"zh": "愿外卖比预计早到，工作比预计早完。", "en": "may food arrive early and work finish even earlier."}, {"zh": "空腹不宜做重大决定，容易把预算算成饭钱。", "en": "avoid major decisions on an empty stomach; budgets may turn into lunch money."}, {"zh": "今天的你值得一顿好饭，理由下次再补。", "en": "you deserve a good meal today; supporting evidence may be submitted later."}, {"zh": "效率低的时候别责怪自己，可能是零食配置不够科学。", "en": "do not blame yourself for low efficiency; your snack setup may be scientifically inadequate."}, {"zh": "下午犯困很正常，太阳都准备下班了。", "en": "afternoon sleepiness is normal; even the sun is preparing to clock out."}, {"zh": "愿你的咖啡负责清醒，甜点负责讲道理。", "en": "let coffee handle alertness and dessert handle emotional reasoning."}, {"zh": "工作是长期合作，午饭才是每日必赴的约会。", "en": "work is a long-term partnership; lunch is the daily appointment you must keep."}, {"zh": "休息五分钟不是偷懒，是防止脑子自动关机。", "en": "a five-minute break is not laziness; it prevents an automatic brain shutdown."}, {"zh": "愿你下班后胃口很好，工作群很安静。", "en": "may your appetite be excellent after work and the group chat wonderfully silent."}, {"zh": "今天的工作餐不必豪华，但必须能安慰灵魂。", "en": "today’s work meal need not be fancy, but it must comfort the soul."}, {"zh": "先喝口水，再决定要不要和世界讲道理。", "en": "drink some water before deciding whether to argue with the world."}, {"zh": "愿你的零食抽屉有货，临时会议没货。", "en": "may your snack drawer be stocked and your calendar run out of surprise meetings."}, {"zh": "今日宜发财，实在不行先发个好心情。", "en": "today favors getting rich; failing that, at least generate a good mood."}, {"zh": "愿你的收入像消息一样频繁，支出像验证码一样谨慎。", "en": "may income arrive frequently and expenses require strict verification."}, {"zh": "好运正在派送，备注写着本人签收。", "en": "good luck is out for delivery, marked recipient only."}, {"zh": "愿你的余额保持低调，数字越来越嚣张。", "en": "may your balance stay discreet while its numbers become increasingly outrageous."}, {"zh": "今天适合努力，也适合突然收到一笔钱。", "en": "today is good for working hard and unexpectedly receiving money."}, {"zh": "愿财神今天定位准确，不要送到隔壁。", "en": "may the god of wealth use accurate navigation and avoid the neighbor."}, {"zh": "今天的好运额度充足，请放心使用。", "en": "today’s luck allowance is fully funded; use it confidently."}, {"zh": "愿你的灵感能落地，落地以后还能盈利。", "en": "may your ideas become real and remain profitable after landing."}, {"zh": "好消息可以迟到，账单最好别抢先。", "en": "good news may arrive late, but bills should not arrive first."}, {"zh": "愿今天所有成本都可控，所有惊喜都超预算。", "en": "may every cost stay controlled and every pleasant surprise exceed expectations."}, {"zh": "今日运势：适合认真赚钱，不适合认真焦虑。", "en": "today’s forecast: excellent for earning and poor for serious worrying."}, {"zh": "愿你的努力产生复利，烦恼停止计息。", "en": "may your effort compound while your worries stop accruing interest."}, {"zh": "愿订单有礼貌地排队，退款按钮保持沉默。", "en": "may orders queue politely while the refund button remains silent."}, {"zh": "今天不一定暴富，但可以先暴露一下实力。", "en": "you may not become rich today, but you can reveal some serious ability."}, {"zh": "愿收入越来越像主角，支出慢慢退居配角。", "en": "may income become the lead character while expenses accept a supporting role."}, {"zh": "机会来了请抓稳，钱来了请抓得更稳。", "en": "hold opportunities firmly and money even more firmly."}, {"zh": "愿今天的好运无需充值，也没有使用期限。", "en": "may today’s luck require no top-up and carry no expiration date."}, {"zh": "先认真生活，发财的事让命运加个急单。", "en": "live seriously and ask fate to mark wealth as an urgent order."}, {"zh": "愿你的钱包终于理解什么叫持续增长。", "en": "may your wallet finally understand sustainable growth."}, {"zh": "发财不必一夜之间，别一夜之间花完就好。", "en": "wealth need not arrive overnight; just avoid spending it overnight."}, {"zh": "愿你今天有预算，有机会，还有一点意外之财。", "en": "may you have a budget, an opportunity, and a little unexpected money today."}, {"zh": "愿你的回报比付出多一点，至少别少得太明显。", "en": "may your return exceed your effort, or at least not fall embarrassingly short."}, {"zh": "如果生活给你柠檬，先看看能不能报销。", "en": "if life gives you lemons, first check whether they are reimbursable."}, {"zh": "愿你的快乐像手机电量，低于百分之二十就提醒。", "en": "may your happiness behave like battery power and warn you below twenty percent."}, {"zh": "生活偶尔跑偏，可能只是想带你看看支线剧情。", "en": "when life goes off course, it may simply be showing you a side quest."}, {"zh": "愿烦恼像袜子一样，洗着洗着少一只。", "en": "may your worries behave like socks and mysteriously lose one in the wash."}, {"zh": "今天先别想太远，快递都还只显示已揽收。", "en": "do not think too far ahead; even the delivery only says collected."}, {"zh": "愿你的好运像 Wi-Fi，走到哪里都自动连接。", "en": "may your luck behave like Wi-Fi and connect automatically wherever you go."}, {"zh": "生活没有暂停键，但你可以假装去接杯水。", "en": "life has no pause button, but you can pretend to refill your water."}, {"zh": "今天开心一点，不然皱纹会以为自己有绩效奖金。", "en": "be happier today or your wrinkles may think they earned a performance bonus."}, {"zh": "愿烦恼像天气预报一样，偶尔也预测不准。", "en": "may your worries be as unreliable as an occasional weather forecast."}, {"zh": "今天适合抬头看看天空，确认它还没有收费。", "en": "look at the sky today while access remains free."}, {"zh": "如果运气没来，先给它发个定位。", "en": "if luck has not arrived, send it your location."}, {"zh": "今天别太严肃，地球转了一整天也没写日报。", "en": "do not be too serious today; Earth rotates all day without submitting a report."}, {"zh": "愿你的心情像自动门，快乐一靠近就打开。", "en": "may your mood be an automatic door that opens whenever happiness approaches."}, {"zh": "生活若没有惊喜，可能只是快递还在路上。", "en": "if life has no surprise yet, the package may still be in transit."}, {"zh": "今天可以走慢一点，影子反正会等你。", "en": "you may walk slowly today; your shadow will wait."}, {"zh": "愿你的快乐没有广告，烦恼可以跳过。", "en": "may your happiness contain no ads and your worries include a skip button."}, {"zh": "今天如果迷路，就当免费解锁了新地图。", "en": "if you get lost today, consider it a free map expansion."}, {"zh": "愿今天的尴尬像电梯门，几秒后自动关闭。", "en": "may today’s awkward moments close automatically like elevator doors."}, {"zh": "今天适合放下包袱，太重还可能超出行李额度。", "en": "today is good for dropping emotional baggage before excess fees apply."}, {"zh": "愿生活偶尔开挂，但别弹出付费窗口。", "en": "may life occasionally activate cheat mode without opening a payment screen."}, {"zh": "今天的你已经很棒了，至少成功起床并打开了软件。", "en": "you are doing well today; you got up and opened the app."}, {"zh": "不必事事完美，你又不是展示样品。", "en": "you do not need perfection; you are not a showroom sample."}, {"zh": "脑子偶尔短路没关系，说明平时确实通电。", "en": "an occasional mental short circuit is fine; it proves the system usually has power."}, {"zh": "今天状态一般也没事，一般人也能完成不一般的事。", "en": "an average mood is fine; ordinary people still complete extraordinary tasks."}, {"zh": "允许自己偶尔迷糊，导航也会重新规划路线。", "en": "allow occasional confusion; even navigation recalculates routes."}, {"zh": "别和别人比速度，你连自己的网速都不稳定。", "en": "do not compare speeds with others; even your own internet speed varies."}, {"zh": "别担心偶尔犯傻，聪明也需要轮休。", "en": "do not worry about silly moments; intelligence needs days off too."}, {"zh": "今天的自信先用着，不够下午再续杯。", "en": "use today’s confidence now and refill it this afternoon if needed."}, {"zh": "你不是效率低，只是做事比较有电影节奏。", "en": "you are not inefficient; your workflow simply has cinematic pacing."}, {"zh": "偶尔忘事不代表老了，可能只是脑内存储满了。", "en": "forgetting things does not mean aging; internal storage may simply be full."}, {"zh": "今天先做个普通天才，不必过度发挥。", "en": "be an ordinary genius today; no need to overperform."}, {"zh": "别怕别人看出你紧张，大家都忙着隐藏自己的紧张。", "en": "do not fear others noticing your nerves; they are busy hiding their own."}, {"zh": "今天不需要无敌，只需要别自动投降。", "en": "you do not need to be invincible today; just avoid surrendering automatically."}, {"zh": "想不明白时先放一放，大脑可能在后台更新。", "en": "when confused, pause; your brain may be updating in the background."}, {"zh": "你不是走得慢，是人生地图加载得比较精细。", "en": "you are not moving slowly; your life map is loading in high detail."}, {"zh": "今天可以不闪耀，但别把自己调成飞行模式。", "en": "you need not shine today, but do not switch yourself to airplane mode."}, {"zh": "犯错以后别只顾尴尬，顺手把经验捡起来。", "en": "after a mistake, do not just feel awkward; pick up the lesson too."}, {"zh": "今天没有满状态也没关系，你又不是游戏角色。", "en": "it is fine not to have full energy today; you are not a game character."}, {"zh": "别把一次失误叫失败，最多叫现场教学。", "en": "do not call one mistake a failure; call it live training."}, {"zh": "今天请对自己客气一点，毕竟你们还要长期合作。", "en": "be polite to yourself today; the two of you have a long-term partnership."}, {"zh": "计划可以很远大，今天先别让第一步继续躺在备忘录里。", "en": "your plan may be ambitious, but do not let the first step keep resting in your notes."}, {"zh": "今天少一点自我感动，多一点真正完成。", "en": "spend less time impressing yourself and more time actually finishing."}, {"zh": "真正的忙会有结果，假装的忙只会有截图。", "en": "real busyness produces results; performative busyness produces screenshots."}, {"zh": "别急着证明自己，时间会替靠谱的人做背景调查。", "en": "do not rush to prove yourself; time conducts background checks for dependable people."}, {"zh": "有些关系不用修复，断开以后网络反而更稳定。", "en": "some connections need no repair; the network becomes more stable after disconnection."}, {"zh": "计划写得像人生逆袭剧本没关系，先把今天这一集拍完。", "en": "your plan may read like a comeback story; just finish today’s episode first."}, {"zh": "想法落地之前大多只是脑内烟花，好看，但暂时不能收款。", "en": "before an idea becomes real, it is mostly mental fireworks—impressive, but not yet payable."}, {"zh": "别总等万事俱备，万事通常没这么配合。", "en": "do not wait for everything to be ready; everything is rarely that cooperative."}, {"zh": "情怀当然可以有，账单只是更喜欢听数字。", "en": "passion is welcome; bills simply prefer numbers."}, {"zh": "目标可以很宏大，第一步最好别一直住在备忘录里。", "en": "the goal may be grand, but the first step should not live forever in your notes."}, {"zh": "忙不是勋章，做完以后才比较像。", "en": "being busy is not a medal; finishing something looks much closer to one."}, {"zh": "别把准备工作做成连续剧，正片也该开播了。", "en": "do not turn preparation into a long-running series; the main feature should begin."}, {"zh": "有些问题并不难，只是你礼貌地绕了它很多圈。", "en": "some problems are not difficult; you have simply circled them very politely."}, {"zh": "现实说话偶尔有点直，但通常比空话更节省时间。", "en": "reality can be blunt, but it usually saves more time than empty talk."}, {"zh": "计划再漂亮也不会自己长出结果，除非它偷偷学会了加班。", "en": "even a beautiful plan will not grow results by itself unless it secretly learned to work overtime."}, {"zh": "收藏再多方法也不会自动升级，知识暂时不支持一键安装。", "en": "collecting more methods will not upgrade you automatically; knowledge still lacks one-click installation."}, {"zh": "随缘适合看天气，做事还是稍微主动一点比较省心。", "en": "going with the flow suits the weather; taking initiative usually works better for getting things done."}, {"zh": "今天可以清醒一点，但不必清醒到把快乐也戒了。", "en": "stay clear-minded today, but not so clear-minded that you quit happiness too."}, {"zh": "别把拖延包装成慎重，包装再精美也还是没开始。", "en": "do not package procrastination as caution; elegant wrapping still does not count as starting."}, {"zh": "方向错了，跑得再快也只是更早叫车回来。", "en": "running faster in the wrong direction only means booking the ride back sooner."}, {"zh": "你已经很努力了，虽然有时候努力的方向像抽奖。", "en": "you have worked hard, even if your direction occasionally resembles a lottery."}, {"zh": "今天别再和自己过不去，你们俩还得一起还房贷。", "en": "stop fighting yourself today; the two of you still have bills to pay together."}, {"zh": "你当然可以拖延，只是未来的你已经在磨刀了。", "en": "you may procrastinate, but your future self is already sharpening a knife."}, {"zh": "别嫌自己进步慢，至少退步的时候也没太快。", "en": "do not complain about slow progress; at least your setbacks are not especially fast either."}, {"zh": "今天要相信自己，别人未必有空替你相信。", "en": "believe in yourself today; others may be too busy to do it for you."}, {"zh": "你可以休息，但别休息到连梦想都以为你搬家了。", "en": "you may rest, but not so long that your dreams think you moved away."}, {"zh": "别总等状态好，状态可能也在等你先动。", "en": "do not keep waiting for motivation; motivation may be waiting for you to move first."}, {"zh": "你不是没有潜力，只是偶尔把潜力当库存压着。", "en": "you are not lacking potential; you occasionally keep it buried like unsold stock."}, {"zh": "今天少怀疑自己一点，竞争对手已经替你做得够多了。", "en": "doubt yourself less today; competitors are already doing enough of that for you."}, {"zh": "你值得更好的结果，但先把眼前这件事做完再说。", "en": "you deserve better results, but finish the task in front of you first."}, {"zh": "别怕丢脸，大家很忙，通常记不住你那点尴尬。", "en": "do not fear embarrassment; people are busy and rarely remember yours."}, {"zh": "你可以偶尔脆弱，但别让脆弱接管财务和日程。", "en": "you may be vulnerable sometimes, but do not let vulnerability manage your money or schedule."}, {"zh": "今天别再说“明天开始”，明天已经听烦了。", "en": "stop saying tomorrow today; tomorrow is tired of hearing it."}, {"zh": "你不是做不到，只是有时特别擅长先想一百遍。", "en": "you are capable; you simply excel at thinking about it one hundred times first."}, {"zh": "别总怕选择错，不选择也会自动产生后果。", "en": "do not fear choosing wrongly; refusing to choose creates consequences too."}, {"zh": "你可以低调，但别低调到机会都认不出你。", "en": "stay humble, but not so invisible that opportunities fail to recognize you."}, {"zh": "今天把脸皮放厚一点，很多机会不提供礼貌提醒。", "en": "grow slightly thicker skin today; opportunities rarely send polite reminders."}, {"zh": "别把所有情绪都当真，有些只是饿了、困了和钱少了。", "en": "do not take every emotion seriously; some are simply hunger, fatigue, and insufficient funds."}, {"zh": "你很好，只是偶尔需要关闭胡思乱想的会员自动续费。", "en": "you are doing fine; you just need to cancel the auto-renewal on overthinking."}, {"zh": "今天可以自信一点，反正过度谦虚也不会自动打折。", "en": "be more confident today; excessive modesty does not generate discounts."}, {"zh": "别羡慕别人轻松，他们没发出来的部分可能比你还乱。", "en": "do not envy someone else’s ease; the unpublished parts may be messier than yours."}, {"zh": "今天少看一点成功学，多做一点成功需要做的事。", "en": "consume less success advice today and do more of what success actually requires."}, {"zh": "没必要和所有人保持联系，有些联系人只负责消耗电量。", "en": "you need not stay connected to everyone; some contacts exist only to drain battery."}, {"zh": "别因为别人声音大，就误以为他们更有道理。", "en": "do not mistake volume for correctness."}, {"zh": "有些人说你变了，其实只是你终于不再方便他们。", "en": "when some people say you changed, it may mean you are no longer convenient for them."}, {"zh": "今天别把别人的期待当任务，他们又没给你发工资。", "en": "do not treat other people’s expectations as assignments; they are not paying you."}, {"zh": "真正关心你的人会问累不累，不只问做完没有。", "en": "people who truly care ask whether you are tired, not only whether you finished."}, {"zh": "别急着原谅所有人，有些人需要先学会道歉。", "en": "do not rush to forgive everyone; some people should learn to apologize first."}, {"zh": "今天可以心软，但别软到别人拿你当地毯。", "en": "you may be soft-hearted today, but not so soft that others use you as a rug."}, {"zh": "有些合作结束不是损失，是成本终于停止增长。", "en": "the end of some partnerships is not a loss; it is cost control finally working."}, {"zh": "别把沉默理解成认输，有时只是懒得陪人表演。", "en": "do not read silence as surrender; sometimes it means refusing to join the performance."}, {"zh": "今天不要替所有人收拾残局，你不是公共售后。", "en": "do not clean up everyone’s mess today; you are not public customer support."}, {"zh": "别人不珍惜你的时间，你就更要替自己珍惜。", "en": "when others do not value your time, value it even more yourself."}, {"zh": "有些门关上不是遗憾，是终于不用再替里面的人操心。", "en": "some closed doors are not regrets; they are freedom from worrying about what is inside."}, {"zh": "今天少一点解释，多一点让结果自己开口。", "en": "explain less today and let results speak."}, {"zh": "别怕被误解，长期靠谱的人最终会自带说明书。", "en": "do not fear being misunderstood; long-term reliability eventually becomes its own manual."}, {"zh": "谁总让你证明价值，谁大概从没打算认真看。", "en": "anyone who constantly demands proof of your worth probably never intended to look carefully."}, {"zh": "今天可以翻篇，但不必把教训也一起删掉。", "en": "turn the page today, but do not delete the lesson."}, {"zh": "有些期待放下以后，不是失望，是终于恢复出厂设置。", "en": "releasing certain expectations is not disappointment; it is a factory reset."}, {"zh": "愿你越来越温柔，也越来越不好糊弄。", "en": "may you become kinder and increasingly difficult to fool."}, {"zh": "开始不必盛大，迈出第一步就已经改变了局面。", "en": "a beginning does not need to be dramatic; the first step already changes the situation."}, {"zh": "把目标拆小，把行动做实，答案会逐渐清楚。", "en": "make the goal smaller, make the action real, and the answer will become clearer."}, {"zh": "真正可靠的进步，往往来自每天多做一点点。", "en": "dependable progress often comes from doing a little more each day."}, {"zh": "不必等状态完美，行动本身会带来状态。", "en": "do not wait for perfect motivation; action often creates it."}, {"zh": "今天完成的雏形，胜过明天想象中的完美。", "en": "a rough version completed today beats a perfect version imagined for tomorrow."}, {"zh": "把注意力放在能改变的事情上，力量就会回来。", "en": "focus on what you can change, and your sense of strength will return."}, {"zh": "路不一定笔直，但每次修正都算前进。", "en": "the path need not be straight; every correction still moves you forward."}, {"zh": "别低估持续行动的力量，它会把普通日子变成结果。", "en": "do not underestimate consistent action; it turns ordinary days into results."}, {"zh": "今天的耐心，是明天效率的一部分。", "en": "today’s patience is part of tomorrow’s efficiency."}, {"zh": "先建立可重复的节奏，再追求偶尔的爆发。", "en": "build a repeatable rhythm before chasing occasional bursts of effort."}, {"zh": "遇到难题时，先问下一步是什么，而不是我行不行。", "en": "when facing difficulty, ask what the next step is—not whether you are capable."}, {"zh": "进步不总有掌声，但会留下越来越稳的底气。", "en": "progress does not always receive applause, but it leaves growing confidence."}, {"zh": "愿你今天少一点自我怀疑，多一个实际动作。", "en": "may today contain less self-doubt and one more concrete action."}, {"zh": "长期主义不是慢，而是不被短期波动带走。", "en": "long-term thinking is not about being slow; it is about not being carried away by short-term swings."}, {"zh": "做正确的事，再把正确的事做得更顺手。", "en": "do the right thing, then make the right thing easier to repeat."}, {"zh": "每解决一个小问题，你都在升级自己的能力。", "en": "every small problem you solve upgrades your ability."}, {"zh": "允许自己边做边学，很多能力都是在路上长出来的。", "en": "allow yourself to learn while doing; many abilities grow along the way."}, {"zh": "真正的突破，常常藏在再坚持一次里面。", "en": "real breakthroughs are often hidden inside one more attempt."}, {"zh": "别让一时的结果，替你定义长期的可能。", "en": "do not let a temporary result define your long-term possibilities."}, {"zh": "今天的你只需要比昨天多明白一点。", "en": "today you only need to understand a little more than yesterday."}, {"zh": "先理解问题，再选择工具；工具只是手段，结果才是目标。", "en": "understand the problem before choosing the tool; tools are means, outcomes are the goal."}, {"zh": "清晰的优先级，往往比更长的工作时间有效。", "en": "clear priorities are often more effective than longer working hours."}, {"zh": "复杂任务不可怕，边界不清才容易消耗。", "en": "complex tasks are manageable; unclear boundaries are what drain energy."}, {"zh": "好的流程不是让人更忙，而是让正确的事更容易发生。", "en": "a good process does not make people busier; it makes the right things easier to happen."}, {"zh": "先完成可用版本，再用真实反馈决定下一步。", "en": "finish a usable version first, then let real feedback decide the next step."}, {"zh": "记录每次判断，未来就能少走一次弯路。", "en": "record each decision so the future can avoid one more detour."}, {"zh": "效率不是做得多，而是减少无意义的重复。", "en": "efficiency is not doing more; it is reducing meaningless repetition."}, {"zh": "发现问题不是失败，是系统开始变可靠的信号。", "en": "finding a problem is not failure; it is a sign the system is becoming reliable."}, {"zh": "数据会告诉你发生了什么，思考决定下一步做什么。", "en": "data tells you what happened; judgment decides what to do next."}, {"zh": "别让漂亮的方案掩盖真实的使用成本。", "en": "do not let an elegant plan hide its real operating cost."}, {"zh": "先验证最危险的假设，成功会更踏实。", "en": "test the riskiest assumption first, and success will stand on firmer ground."}, {"zh": "能被解释清楚的流程，才更容易被稳定执行。", "en": "a process that can be explained clearly is easier to execute consistently."}, {"zh": "今天解决根因，明天就少处理一次表面问题。", "en": "solve the root cause today and avoid another surface fix tomorrow."}, {"zh": "成熟不是没有错误，而是错误越来越容易被发现和修正。", "en": "maturity is not the absence of errors; it is making errors easier to detect and correct."}, {"zh": "边界明确，合作才高效；目标明确，行动才不跑偏。", "en": "clear boundaries improve collaboration, and clear goals keep action on course."}, {"zh": "真正省时间的办法，通常是先花时间把规则想清楚。", "en": "the real way to save time is often to spend time clarifying the rules first."}, {"zh": "把经验写下来，个人能力才会逐渐变成可复用资产。", "en": "write experience down so personal ability can become a reusable asset."}, {"zh": "少一点无目的优化，多一点面向结果的改进。", "en": "do less aimless optimization and more outcome-driven improvement."}, {"zh": "好的判断不是永远正确，而是能根据新证据及时调整。", "en": "good judgment is not always right; it adjusts promptly when new evidence appears."}, {"zh": "先保证准确，再追求速度，最后才谈自动化。", "en": "secure accuracy first, then speed, and only then automation."}, {"zh": "累的时候先休息，不必把疲惫解释成不够努力。", "en": "rest when you are tired; fatigue does not mean you are not trying hard enough."}, {"zh": "允许今天只是普通的一天，也允许自己只是平常的自己。", "en": "allow today to be ordinary and allow yourself to be simply human."}, {"zh": "有些答案需要时间，不必逼今天立刻交卷。", "en": "some answers need time; today does not have to submit everything immediately."}, {"zh": "慢下来不是退后，是给判断留出空间。", "en": "slowing down is not retreating; it creates room for better judgment."}, {"zh": "愿你在忙碌里仍能听见自己的感受。", "en": "may you still hear your own feelings amid a busy day."}, {"zh": "不用把每件事都背在心上，桌面也需要定期清理。", "en": "you do not need to carry everything in your heart; even a desktop needs regular clearing."}, {"zh": "今天做不到的事，可以交给明天更有力气的自己。", "en": "what cannot be done today may be handed to tomorrow’s better-rested self."}, {"zh": "愿你知道什么时候坚持，也知道什么时候放过自己。", "en": "may you know when to persist and when to give yourself a break."}, {"zh": "生活不是持续冲刺，走稳也能到达。", "en": "life is not a continuous sprint; steady steps can still get you there."}, {"zh": "别急着否定自己，也许你只是经历了一个不顺的上午。", "en": "do not reject yourself too quickly; perhaps it was simply a difficult morning."}, {"zh": "愿你把注意力从遗憾收回来，放到仍能创造的部分。", "en": "may you bring your attention back from regret to what you can still create."}, {"zh": "心情低一点没关系，太阳也不是每时每刻都在头顶。", "en": "it is okay for your mood to dip; the sun is not overhead every hour either."}, {"zh": "先照顾好自己，再去处理世界的复杂。", "en": "take care of yourself before handling the world’s complexity."}, {"zh": "愿你不因一次停顿，就怀疑整段旅程。", "en": "may one pause never make you doubt the whole journey."}, {"zh": "今天少做一点，也可以把那一点做得安心。", "en": "doing less today is fine; let that smaller amount be done with peace."}, {"zh": "你可以认真生活，也可以偶尔什么都不证明。", "en": "you can live earnestly without having to prove something every day."}, {"zh": "愿你在追求更好时，也不忘记现在已经不错。", "en": "while reaching for better, remember that the present may already be good."}, {"zh": "不必时时坚强，诚实面对疲惫也是一种力量。", "en": "you do not need to be strong at all times; honestly facing tiredness is also strength."}, {"zh": "愿你的心里有窗，忙的时候也能透进一点光。", "en": "may there be a window in your heart, letting in light even on busy days."}, {"zh": "今天先把呼吸放慢，再把事情想清楚。", "en": "slow your breathing first, then think the situation through."}, {"zh": "愿今天的机会刚好出现，你也刚好准备好了。", "en": "may the right opportunity appear just as you are ready for it."}, {"zh": "愿好事有迹可循，也有意外惊喜。", "en": "may good things arrive through both steady progress and unexpected surprises."}, {"zh": "愿你今天做出的选择，日后回看仍觉得明智。", "en": "may today’s choices still look wise when you revisit them later."}, {"zh": "愿你一路有判断、有运气，也有人情味。", "en": "may your path include sound judgment, good luck, and human kindness."}, {"zh": "愿你想到的办法能落地，期待的结果能靠近。", "en": "may your ideas become workable and your hoped-for results draw closer."}, {"zh": "愿今天适合开始，也适合完成。", "en": "may today be good for both beginning and finishing."}, {"zh": "愿你避开无效消耗，把力气用在真正重要的地方。", "en": "may you avoid wasted effort and spend your energy where it truly matters."}, {"zh": "愿你今天有一件事情，比预期更顺利。", "en": "may at least one thing go better than expected today."}, {"zh": "愿你的努力被时间放大，而不是被焦虑打折。", "en": "may time amplify your effort instead of anxiety discounting it."}, {"zh": "愿你遇见靠谱的人，也成为靠谱的人。", "en": "may you meet dependable people and remain dependable yourself."}, {"zh": "愿今天的决定带来明天更大的选择空间。", "en": "may today’s decisions create more options for tomorrow."}, {"zh": "愿你的计划不只顺利开始，也能稳稳收尾。", "en": "may your plan not only start smoothly but finish steadily."}, {"zh": "愿你今天少遇阻力，多遇助力。", "en": "may today bring fewer obstacles and more support."}, {"zh": "愿你所做的准备，在关键时刻恰好派上用场。", "en": "may your preparation prove useful at exactly the right moment."}, {"zh": "愿今天的每次尝试，都比上一次更接近答案。", "en": "may every attempt today move closer to the answer."}, {"zh": "愿你有把握时果断，没把握时谨慎。", "en": "may you act decisively when confident and carefully when uncertain."}, {"zh": "愿好消息正在路上，坏情绪已经返程。", "en": "may good news be on its way while bad moods head home."}, {"zh": "愿你今天的付出不被辜负，判断不被噪声干扰。", "en": "may your effort be rewarded and your judgment stay clear of noise."}, {"zh": "愿你今天遇到的每个转弯，都通向更合适的方向。", "en": "may every turn you meet today lead toward a better direction."}, {"zh": "愿你做出的每份努力，都在合适的时候收到回音。", "en": "may every effort you make receive an answer at the right time."}, {"zh": "千里之行，始于足下；先走好眼前这一步。", "en": "a journey of a thousand miles begins beneath your feet; take the next step well."}, {"zh": "知之为知之，不知为不知；清楚边界也是智慧。", "en": "know what you know and recognize what you do not; clarity about limits is wisdom."}, {"zh": "工欲善其事，必先利其器；但别忘了先确认要做什么。", "en": "good work benefits from good tools—but first confirm what work truly matters."}, {"zh": "三人行，必有我师；每次合作都可能带来新方法。", "en": "among any three people there is something to learn; every collaboration may reveal a better method."}, {"zh": "学而时习之，能力会在反复实践中变得可靠。", "en": "learning becomes dependable through repeated practice."}, {"zh": "欲速则不达；稳住关键步骤，往往反而更快。", "en": "excessive haste can delay arrival; steady handling of key steps is often faster."}, {"zh": "不积跬步，无以至千里；今天的小进展也有分量。", "en": "without small steps there is no long journey; today’s small progress matters."}, {"zh": "锲而不舍，金石可镂；持续比一时用力更重要。", "en": "persistent effort can carve stone; consistency matters more than a brief burst."}, {"zh": "纸上得来终觉浅，真实测试会让判断更扎实。", "en": "knowledge from paper alone remains shallow; real testing makes judgment stronger."}, {"zh": "山重水复疑无路，拆开问题后常会出现新出口。", "en": "when the road seems closed, breaking down the problem often reveals another way."}, {"zh": "长风破浪会有时，愿你保持准备，也保持耐心。", "en": "the wind will eventually favor the prepared; keep both readiness and patience."}, {"zh": "沉舟侧畔千帆过，变化之中也藏着新的机会。", "en": "even beside a sunken boat, new sails pass by; change can carry fresh opportunities."}, {"zh": "会当凌绝顶，但今天先把上山的第一段走稳。", "en": "the summit may be the goal, but today’s task is to walk the first section steadily."}, {"zh": "海纳百川，有容乃大；听得进不同意见，判断才更完整。", "en": "broad judgment grows from making room for different views."}, {"zh": "兼听则明，偏信则暗；重要决定值得多看一面。", "en": "listening widely brings clarity; important decisions deserve more than one perspective."}, {"zh": "前事不忘，后事之师；记录错误，是为了减少重复。", "en": "remember what happened before so it can guide what comes next; record errors to avoid repeating them."}, {"zh": "凡事预则立；适度准备，会让行动更从容。", "en": "preparation helps things stand; enough planning makes action calmer."}, {"zh": "一张一弛，文武之道；工作与休息都应有节奏。", "en": "effort and rest should alternate; both belong to a sustainable rhythm."}, {"zh": "行到水穷处，坐看云起时；暂时无路，也可以先观察。", "en": "when the path ends, pause and watch the clouds rise; observation can be part of progress."}, {"zh": "莫愁前路无知己，认真做事终会遇到同行者。", "en": "do not fear walking alone; sincere work often leads to worthy companions."}]"""


@dataclass(frozen=True)
class Greeting:
    zh: str
    en: str


GREETINGS: tuple[Greeting, ...] = tuple(
    Greeting(
        zh=_strip_zh_prefix(item["zh"]),
        en=_strip_en_prefix(item["en"]),
    )
    for item in json.loads(_GREETINGS_JSON)
)

if len(GREETINGS) != 288:
    raise RuntimeError("内置问候语数量必须为 288 条")


@dataclass
class HeaderBinding:
    title_label: QLabel
    subtitle_label: QLabel
    shuffle_button: QPushButton
    user_name_label: QLabel | None = None


DEFAULT_DISPLAY_NAME = "用户"
_USER_NAME_QSS = (
    "background:#176ff2;color:white;border-radius:8px;"
    "padding:4px 14px;font-weight:600;font-size:11pt;"
)
_HI_LABEL_QSS = (
    "font-family:\"Segoe UI Semibold\",\"Microsoft YaHei UI\";"
    "font-size:15pt;font-weight:600;color:#172033;"
)
_SUBTITLE_QSS = "color:#738198;font-size:9pt;"


class GreetingHeaderController(QObject):
    """
    一个控制器可绑定所有页面的现有标题区。

    display_name_provider：
    直接读取软件现有设置中的"显示名称"（1-8 字符，空时回退"用户"）。
    """

    def __init__(
        self,
        display_name_provider: Callable[[], str],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._display_name_provider = display_name_provider
        self._bindings: list[HeaderBinding] = []
        self._current_index: int | None = None

        # 每次软件启动/用户重新进入本次界面会话时随机一次。
        self.show_random()

    def bind_existing_header(
        self,
        *,
        title_label: QLabel,
        subtitle_label: QLabel,
        shuffle_button: QPushButton,
        user_name_label: QLabel | None = None,
    ) -> None:
        """将页面现有的标题/副标题/用户名/Hi 标签绑定为统一问候布局。

        要求（人工验收）：
        - 英文副标题必须可见；
        - 用户名使用蓝色圆角背景框，宽度随内容变化；
        - 中文正文放标题，英文正文放副标题；
        - "Hi" 在单独的 QLabel 中显示。
        """
        binding = HeaderBinding(
            title_label=title_label,
            subtitle_label=subtitle_label,
            shuffle_button=shuffle_button,
            user_name_label=user_name_label,
        )
        self._bindings.append(binding)

        shuffle_button.setToolTip("刷新欢迎语")

        # 加载刷新图标
        icon_path = resource_path("src/profit_accounting_26/ui/assets/refresh_welcome.svg")
        if icon_path.exists():
            shuffle_button.setIcon(QIcon(str(icon_path)))
            shuffle_button.setIconSize(QSize(22, 22))
        else:
            shuffle_button.setText("↻")

        shuffle_button.clicked.connect(self.show_random)

        # 英文副标题必须可见（之前版本错误地隐藏了）
        subtitle_label.setVisible(True)

        # 将用户名与文本区域设置为 PlainText 格式，避免不必要的 RichText 拼接
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        subtitle_label.setTextFormat(Qt.TextFormat.PlainText)

        # 用户名蓝色背景与字体 - 直接 setStyleSheet 确保在真实 APP_STYLE 下生效
        if user_name_label is not None:
            user_name_label.setStyleSheet(_USER_NAME_QSS)
            user_name_label.setTextFormat(Qt.TextFormat.PlainText)

        self._render_binding(binding)

    @Slot()
    def show_random(self) -> None:
        """随机显示另一条；只有一条数据时允许重复。"""
        if not GREETINGS:
            return

        if len(GREETINGS) == 1:
            new_index = 0
        else:
            candidates = [
                index
                for index in range(len(GREETINGS))
                if index != self._current_index
            ]
            new_index = random.SystemRandom().choice(candidates)

        self._current_index = new_index
        self._render_all()

    def refresh_display_name(self) -> None:
        """
        用户在设置中保存新的显示名称后调用。
        保持当前语录，只更新用户名；背景框内容与中英文问候立即刷新。
        """
        self._render_all()

    def _render_all(self) -> None:
        for binding in self._bindings:
            self._render_binding(binding)

    def _render_binding(self, binding: HeaderBinding) -> None:
        if self._current_index is None:
            return

        greeting = GREETINGS[self._current_index]
        display_name = self._normalized_display_name()

        # 蓝色背景框用户名（PlainText，无需 HTML escape 也不会被解释为 RichText）
        if binding.user_name_label is not None:
            binding.user_name_label.setText(display_name)

        # 中文正文 → 标题；英文正文 → 副标题
        binding.title_label.setText(greeting.zh)
        binding.subtitle_label.setText(greeting.en)

    def _normalized_display_name(self) -> str:
        try:
            value = str(self._display_name_provider()).strip()
        except Exception:
            value = ""
        return value or DEFAULT_DISPLAY_NAME
