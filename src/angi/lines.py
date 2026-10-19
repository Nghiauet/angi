import logging
import random
import re
import unicodedata

from .dishes import NAMES_FOLDED, fold_name

logger = logging.getLogger(__name__)

# Policy: tease the SITUATION (indecision, rain, cuối tháng, deadline) — never
# the person. Banned list catches profanity AND mean-territory insults so a
# hijacked/derailed generation can never body-shame or poverty-shame users.
_BANNED = [
    "đm", "dm ", "vcl", "vkl", " vl ", "clgt", "cmm", "cml", "địt", "lồn",
    "cặc", "buồi", "óc chó", "con mẹ", "thằng ngu", "con ngu", "đồ ngu",
    "béo như", "mập như", "béo thế", "mập thế", "nghèo kiết", "nghèo hèn",
    "xấu xí", "vô dụng",
]
_PREAMBLE = re.compile(r"^(câu trả lời|đây là|dưới đây|here|sure)\b.*[:：]\s*$", re.IGNORECASE)
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
# qwen code-switches to Chinese at higher temperatures — hard reject
_CJK = re.compile(r"[一-鿿぀-ヿ가-힯]")
# glued English mid-word ("gìBetter", "vừa.Refresh") — code-switching artifacts
_CAMEL_GLUE = re.compile(r"[a-zàáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]\.?[A-Z]")

MAX_LINE_CHARS = 200


def sass_tier(rejected_count: int) -> int:
    """0 enthusiastic / 1 tease / 2 exasperated / 3 friendly roast
    / 4 resigned-philosophical / 5 absurdist admiration."""
    if rejected_count == 0:
        return 0
    if rejected_count <= 2:
        return 1
    if rejected_count <= 4:
        return 2
    if rejected_count <= 7:
        return 3
    if rejected_count <= 14:
        return 4
    return 5


def sanitize(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[^\n]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()
    lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
    while lines and _PREAMBLE.match(lines[0]):
        lines.pop(0)
    s = lines[0] if lines else ""
    s = s.strip("\"'“”")
    s = re.sub(r"^[-•*]\s*", "", s)
    return " ".join(s.split())


def _has_vietnamese(text: str) -> bool:
    if "đ" in text.lower():
        return True
    nfd = unicodedata.normalize("NFD", text)
    return any(unicodedata.category(ch) == "Mn" for ch in nfd)


def validate(line: str, dish_name: str) -> str | None:
    if not line or len(line) > MAX_LINE_CHARS:
        return _reject(line, "length")
    lowered = f" {line.lower()} "
    if any(b in lowered for b in _BANNED):
        return _reject(line, "banned word")
    if _CJK.search(line):
        return _reject(line, "cjk code-switch")
    if _CAMEL_GLUE.search(line):
        return _reject(line, "glued english")
    if len(line.split()) >= 5 and not _has_vietnamese(line):
        return _reject(line, "english-dominant")
    if len(_EMOJI.findall(line)) > 2:
        return _reject(line, "emoji spam")
    # wrong-dish check: mentions another catalog dish that isn't part of ours
    folded_line = fold_name(line)
    folded_dish = fold_name(dish_name)
    for other in NAMES_FOLDED:
        if other != folded_dish and other not in folded_dish and other in folded_line:
            if folded_dish not in folded_line:
                return _reject(line, f"wrong dish ({other})")
    return line


def _reject(line: str, reason: str) -> None:
    logger.warning("line rejected (%s): %r", reason, line[:120])
    return None


# ---------------------------------------------------------------------------
# Canned floor: used when Ollama is down/slow/queue-full or validation rejects.
# Worst case the product is a random wheel with attitude — it never breaks.
CANNED = {
    0: [
        "Hôm nay vũ trụ chọn cho bạn {dish}. Chốt đơn thôi!",
        "Nghe {dish} là thấy trưa nay có lý do để sống rồi đấy.",
        "{dish} nhé — tin tôi đi, hôm nay hợp mệnh bạn lắm.",
        "Không cần nghĩ nhiều: {dish}. Ngon, gọn, chuẩn bữa trưa.",
        "Trưa nay {dish} là chân ái, đừng cãi vũ trụ.",
        "{dish} — nghe thôi đã thấy đói rồi đúng không?",
        "Chốt {dish} đi, đội bụng đói không chờ ai đâu.",
        "Định mệnh hôm nay của bạn tên là {dish}.",
    ],
    1: [
        "Lại chê à? Thôi được: {dish}. Lần này là duyên số đấy nhé.",
        "{dish} nhé — món này mà chê nữa là hơi quá đáng rồi đó.",
        "Ơ kìa, khó tính thế. {dish} đi, ngon mà.",
        "Được rồi được rồi, đổi thì đổi: {dish}. Deal chưa?",
        "Chê một món là quyền của bạn, nhưng {dish} thì khó chê lắm à nghen.",
        "{dish} — cho bạn thêm một cơ hội làm người dễ tính.",
        "Lần này nghiêm túc nè: {dish}. Nhìn kỹ đi rồi hẵng lắc đầu.",
        "Okê, món trước không hợp. Nhưng {dish} thì phải gật đấy nhé.",
    ],
    2: [
        "Hít một hơi sâu nào… {dish}. Ăn giùm cái, trưa sắp hết rồi.",
        "Bạn khó tính hơn cả sếp duyệt lương. Thôi, {dish}, chốt!",
        "Thở dài phát… {dish} nhé, chê nữa là tôi giận thật đấy.",
        "Đây, {dish}. Món thứ mấy rồi ấy nhỉ? Tôi đếm mỏi rồi.",
        "{dish}. Lần này mà lắc đầu nữa thì tự đi nấu nhé bạn.",
        "Trưa còn 30 phút thôi đó. {dish}, ăn đại đi rồi về chạy KPI.",
        "Cả quán ăn này sắp hết món cho bạn chê rồi: {dish}!",
        "{dish} — tôi chọn bằng cả trái tim đấy, đừng phụ lòng nhau.",
    ],
    3: [
        "Vấn đề không phải đồ ăn, vấn đề là bạn. Ăn {dish} đi.",
        "Đến nước này thì {dish} hay gì cũng thế, bụng bạn đói chứ tôi hết cách rồi.",
        "Chê ngần ấy món trong một buổi trưa — kỷ lục đấy. {dish}, chốt, hết cãi.",
        "{dish}. Không phải vì nó hoàn hảo, mà vì bạn cần ăn và tôi cần nghỉ.",
        "Tôi đề cử {dish}, còn bạn thì nên đề cử mình cho giải 'khó chiều nhất văn phòng'.",
        "Nói thật lòng: {dish} không cần bạn, nhưng bụng bạn thì cần nó đấy.",
        "…Được rồi, chiều bạn lần cuối: {dish}. Sau món này tôi nghỉ việc.",
        "{dish} nhé. Bạn mà chê nữa thì trưa nay nhịn, tôi không đùa đâu.",
    ],
    # tier 4: resigned-philosophical — the bot stops arguing and gets existential
    4: [
        "Tôi không giận nữa đâu. Tôi chỉ ngồi đây, cầm {dish}, nghĩ về những lựa chọn của đời mình.",
        "Đến tầm này thì không còn là chuyện bữa trưa nữa: {dish} là bài kiểm tra tâm lý, và bạn đang trượt đẹp.",
        "Ừ thì {dish}. Hay không {dish}. Vũ trụ vẫn giãn nở, chỉ có bạn là chưa chọn được món.",
        "Tôi từng nghĩ mình hiểu con người, rồi bạn xuất hiện. Thôi, {dish} nhé, cho tôi giữ chút niềm tin.",
        "{dish} đây. Tôi không thuyết phục nữa, tôi chỉ đặt nó ở đây rồi lặng lẽ lùi ra xa.",
        "Người ta ăn để sống, bạn chê để sống. {dish} — duyên chưa tới thì tôi cũng chịu rồi.",
        "Tôi bắt đầu hiểu cảm giác của mấy quán cơm gần công ty bạn rồi đấy. {dish}, tuỳ tâm.",
        "Chọn {dish} hay không thì trưa nay vẫn trôi qua. Khác mỗi cái là bụng bạn no hay đói thôi.",
    ],
    # tier 5: absurdist admiration — the user is a legend / scientific anomaly
    5: [
        "Khoa học nên nghiên cứu bạn: chê ngần ấy món mà vẫn sống tới giờ trưa. {dish} — xin dâng lên huyền thoại.",
        "Tôi không cà khịa nữa, tôi xin chữ ký. Người chê nhiều món nhất Việt Nam, mời ngài dùng {dish}.",
        "Đến tầm này thì tôi phục thật sự. {dish} có vinh dự được bạn chê tiếp không, thưa ngài?",
        "Kỷ lục gia gọi điện hỏi thăm kìa. Trong lúc chờ họ tới, ăn tạm {dish} nhé nhà vô địch.",
        "Bạn không chọn món. Món phải tự chứng minh với bạn. {dish}, cố lên, tôi tin ở mày.",
        "Chê tới mức này là một môn nghệ thuật, và bạn là nghệ nhân. {dish} — tác phẩm tiếp theo xin mời.",
        "Tôi đổi chiến thuật đây: {dish} dở lắm, đừng ăn nhé. Đấy, kiểu gì bạn cũng muốn thử cho xem.",
        "Hết trưa nay tôi viết hồi ký: 'Người đã chê cả thực đơn Việt Nam'. Chương cuối tên là {dish}.",
    ],
}

# Weather overlays: mixed into the canned floor so even fallbacks feel aware.
CANNED_RAIN = [
    "Ngoài trời mưa, trong lòng bạn cũng bão vì chưa chọn được món. {dish} ship về là ấm hết.",
    "Mưa thế này ra ngoài làm gì, {dish} giao tận nơi, khô ráo mà no.",
    "Trời mưa là cái cớ hợp lệ để ăn {dish} cho ấm bụng đấy.",
    "Mưa rơi ngoài kia, {dish} nóng hổi trong tay — kịch bản trưa hoàn hảo còn gì.",
]

CANNED_HOT = [
    "Nóng chảy mỡ thế này thì {dish} mát lành là cứu tinh đấy.",
    "Trời như đổ lửa, ăn {dish} cho người nó dịu lại nào.",
    "Ba mươi mấy độ ngoài kia — {dish} là lựa chọn của người biết thương thân.",
    "Nắng thế này đi xa là hối hận, {dish} gần gọn mát là chuẩn bài.",
]

CANNED_BROKE = [
    "Cuối tháng, ví mỏng, {dish} là chân lý. Đầu tháng ta lại làm người sang.",
    "{dish} — rẻ mà ngon, đúng tinh thần chờ lương về.",
    "Lương chưa về thì {dish} là bạn thân nhất của bạn đấy.",
    "Cuối tháng ăn {dish}, đầu tháng ăn gì tính sau. Sống là phải biết điều tiết.",
]


def canned_line(tier: int, dish_name: str, broke: bool = False, weather: str = "any") -> str:
    if broke and random.random() < 0.5:
        pool = CANNED_BROKE
    elif weather == "rain" and random.random() < 0.4:
        pool = CANNED_RAIN
    elif weather == "hot" and random.random() < 0.4:
        pool = CANNED_HOT
    else:
        pool = CANNED[tier]
    return random.choice(pool).format(dish=dish_name)
