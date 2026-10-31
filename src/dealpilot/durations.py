"""Conservative English/Arabic delivery deadlines, using only the standard library.

Calendar arithmetic is anchored to a recorded inquiry timestamp in Saudi time.
Unknown, approximate, business-day and contradictory deadlines require clarification.
"""
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import re
from typing import Any, List, Literal, Optional
from zoneinfo import ZoneInfo
from pydantic import Field
from .models import Model

ZONE = "Asia/Riyadh"
_TRANSLATE = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹أإآ‐‑‒–—", "01234567890123456789ااا-----")
_SMALL = dict(zip("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split(), range(20)))
_TENS = dict(zip("twenty thirty forty fifty sixty seventy eighty ninety".split(), range(20, 100, 10)))
_AR_NUMBERS = {"واحد":1, "واحدة":1, "اثنان":2, "اثنين":2, "اثنتان":2, "اثنتين":2, "ثلاث":3, "ثلاثة":3, "اربع":4, "اربعة":4, "خمس":5, "خمسة":5, "ست":6, "ستة":6, "سبع":7, "سبعة":7, "ثمان":8, "ثمانية":8, "تسع":9, "تسعة":9, "عشر":10, "عشرة":10}
_WORDS = "|".join(list(_SMALL) + list(_TENS) + list(_AR_NUMBERS))
_AMOUNT = rf"(?:\d+|(?:{_WORDS})(?:[\s-]+(?:{_WORDS}|hundred|and))*)"
_AR_UNITS = {"يوم":"day", "ايام":"day", "اسبوع":"week", "اسابيع":"week", "شهر":"month", "اشهر":"month", "شهور":"month", "سنة":"year", "سنوات":"year", "عام":"year", "اعوام":"year"}
_DUALS = {"يومين":"day", "يومان":"day", "اسبوعين":"week", "اسبوعان":"week", "شهرين":"month", "شهران":"month", "سنتين":"year", "سنتان":"year", "عامين":"year", "عامان":"year"}
_UNITS = "|".join(sorted(list(_AR_UNITS) + list(_DUALS), key=len, reverse=True))
_DURATION = re.compile(rf"(?<![\w./+-])(?P<amount>{_AMOUNT})[\s-]+(?:(?P<mode>calendar|business|working)[\s-]+)?(?P<unit>days?|weeks?|months?|years?|{_UNITS})\b", re.I)
_AR_SINGLE = re.compile(rf"\b(?:خلال|بعد|في)\s+(?P<unit>{_UNITS})\b")
_MONTHS = {name.lower():n for n,name in enumerate(calendar.month_name) if name}
_AR_MONTHS = dict(zip("يناير فبراير مارس ابريل مايو يونيو يوليو اغسطس سبتمبر اكتوبر نوفمبر ديسمبر".split(), range(1,13)))
_MONTH_DATE = re.compile(rf"\b(?P<month>{'|'.join(_MONTHS)})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,)?\s+(?P<year>\d{{4}})\b", re.I)
_AR_DATE = re.compile(rf"\b(?P<day>\d{{1,2}})\s+(?P<month>{'|'.join(_AR_MONTHS)})\s+(?P<year>\d{{4}})\b")
_ISO_DATE = re.compile(r"(?<!\d)(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?!\d)")
_WEEKDAYS = dict(zip("monday tuesday wednesday thursday friday saturday sunday".split(), range(7)))
_AR_WEEKDAYS = {"الاثنين":0, "الثلاثاء":1, "الاربعاء":2, "الخميس":3, "الجمعة":4, "السبت":5, "الاحد":6}
_NEXT_DAY = re.compile(rf"\bnext\s+(?P<en>{'|'.join(_WEEKDAYS)})\b|\b(?P<ar>{'|'.join(_AR_WEEKDAYS)})\s+القادم(?:ة)?\b", re.I)
_END_MONTH = re.compile(r"\bend of next month\b|نهاية الشهر القادم", re.I)
_URGENCY = re.compile(r"\bASAP\b|\bas soon as possible\b|\burgent\b|في اسرع وقت|باسرع وقت|عاجل", re.I)
_DELIVERY = re.compile(r"\b(?:deliver\w*|timeline|implementation|deploy\w*|rollout|go.live|target)\b|تسليم|تنفيذ|اطلاق|الموعد", re.I)
_OTHER = re.compile(r"\b(?:subscription|licen[cs]e|warranty|support|retention|payment|billing|contract)\b|اشتراك|ضمان|دعم|سداد", re.I)


class Timeline(Model):
    kind: Literal["duration", "date", "relative", "urgency", "unknown"] = "unknown"
    original_text: str = ""
    source_phrase: str = ""
    duration_value: Optional[int] = None
    unit: Optional[Literal["day", "week", "month", "year"]] = None
    deadline: Optional[date] = None
    precision: Literal["exact", "approximate", "tentative", "unknown"] = "unknown"
    constraint: Literal["target", "latest", "preferred", "approximate", "urgency"] = "target"
    explicitly_confirmed: bool = False
    reference_at: Optional[datetime] = None
    timezone: str = ZONE
    requested_days: Optional[int] = Field(default=None, ge=1)
    clarifications: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)

    @property
    def source(self):
        return self.source_phrase or None

    @property
    def issues(self):
        return tuple(self.clarifications)


def inquiry_time(value: Optional[Any]) -> Optional[datetime]:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Inquiry timestamp must include a timezone")
    return parsed.astimezone(ZoneInfo(ZONE))


def _number(text):
    text = text.lower()
    if text.isdigit():
        return int(text) if len(text) <= 5 else None
    if text in _AR_NUMBERS:
        return _AR_NUMBERS[text]
    parts = re.split(r"[\s-]+", text)
    hundreds = 0
    if len(parts) >= 2 and parts[0] in _SMALL and 1 <= _SMALL[parts[0]] <= 9 and parts[1] == "hundred":
        hundreds, parts = _SMALL[parts[0]] * 100, parts[2:]
        if parts[:1] == ["and"]:
            parts = parts[1:]
        if not parts:
            return hundreds
    if len(parts) == 1 and parts[0] in _SMALL:
        return hundreds + _SMALL[parts[0]]
    if parts and parts[0] in _TENS and (len(parts) == 1 or len(parts) == 2 and parts[1] in _SMALL and 1 <= _SMALL[parts[1]] <= 9):
        return hundreds + _TENS[parts[0]] + (_SMALL[parts[1]] if len(parts) == 2 else 0)
    return None


def _add_months(start, count):
    total = start.year * 12 + start.month - 1 + count
    year, month = divmod(total, 12)
    month += 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def _scope(text, start, end):
    prefix = re.split(r"[.!?;\n]", text[:start])[-1]
    delivery, other = list(_DELIVERY.finditer(prefix)), list(_OTHER.finditer(prefix))
    if other and (not delivery or other[-1].start() > delivery[-1].start()):
        # Attributive durations put the delivery cue AFTER the amount/unit.
        post_delivery = re.match(r"\s+(?:delivery|implementation|deployment|rollout)\b", text[end:], re.I)
        available_within = other[-1].group(0).lower() in ("support", "subscription", "license", "licence") and re.search(r"(?:within|no later than)\s+(?:an?\s+)?$", prefix[other[-1].end():], re.I)
        if not post_delivery and not available_within:
            return False
    return not re.match(r"\s+(?:of\s+)?(?:subscription|contract|support|warranty)\b", text[end:], re.I)


def normalize_timeline(text: str, explicit_days: Optional[int] = None, explicit_source: Optional[str] = None,
                       reference_at: Optional[Any] = None, source_hint: Optional[str] = None) -> Timeline:
    reference = inquiry_time(reference_at)
    start_date = reference.date() if reference else None
    normalized = text.translate(_TRANSLATE)
    candidates, questions, notes, occupied = [], [], [], []
    if source_hint and source_hint not in text:
        questions.append("Which delivery phrase did the customer actually state? The extracted source was not found in the inquiry.")
        source_hint = None

    def add(match, kind, value=None, unit=None, deadline=None, problem=None):
        a,b = match.span()
        if not _scope(normalized, a,b):
            return
        if kind == "date" and re.match(r"(?:T\d{2}:|\s+(?:at\s+)?(?:\d{1,2}(?::\d{2}|\s*[ap]m)|noon|midnight))", normalized[b:], re.I):
            problem = "Please confirm a date-only delivery deadline in Saudi time; time-of-day deadlines need separate confirmation."
        if kind == "date":
            context = re.split(r"[.!?;\n]", normalized[:a])[-1]
            date_cue = _DELIVERY.search(context) or re.search(r"\b(?:by|before|on|deadline)\s*$|بحلول\s*$|قبل\s*$", context, re.I)
            if not date_cue and not (source_hint and match.group(0) in source_hint.translate(_TRANSLATE)) and normalized.strip() != match.group(0):
                return
        # Keep attributive wording and qualifiers, not just the numeric token.
        if kind == "duration":
            suffix = re.match(r"(?:\s+(?:delivery|implementation|deployment|rollout)(?:\s+(?:timeline|timeframe|time frame|period|window))?|\s+(?:timeline|timeframe|time frame|period|window)|\s+from now)\b", normalized[b:], re.I)
            if suffix:
                b += suffix.end()
        prefix = normalized[max(0,a-70):a]
        modifiers = r"(?:approximately|about|around|ideally|no later than|within|by|in|خلال|بعد|بحلول|تقريبا|يفضل)"
        qualifier = re.search(rf"(?:(?:delivery|implementation|deployment|rollout)\s+)?(?:{modifiers}\s+)*(?:a|an)\s+$|(?:(?:delivery|implementation|deployment|rollout)\s+)?(?:{modifiers}\s+)+$", prefix, re.I)
        if qualifier:
            a -= len(qualifier.group(0))
        phrase = text[a:b]
        nearby = normalized[a:b].lower()
        precision, constraint = "exact", "target"
        if re.search(r"approximately|\babout\b|\baround\b|تقريبا", nearby):
            precision, constraint = "approximate", "approximate"
        elif re.search(r"ideally|يفضل", nearby):
            precision, constraint = "tentative", "preferred"
        elif re.search(r"within|no later than|\bby\b|خلال|بحلول", nearby):
            constraint = "latest"
        confirmed = bool(re.search(r"(?:confirmed|firm|fixed)\s+(?:delivery\s+)?(?:timeline|deadline|target)\s*(?:is|:)?\s*$|(?:timeline|deadline|target)\s+(?:is\s+)?(?:confirmed|firm|fixed)\s*(?:for|at|:)?\s*$|(?:موعد|تسليم)\s+مؤكد\s*$", normalized[max(0,a-80):a], re.I))
        days = None
        local_questions = []
        if problem:
            precision = "unknown"
            local_questions.append(problem)
        elif kind == "duration":
            if not value or value < 1:
                local_questions.append("How many positive whole calendar days, weeks, months or years are required for delivery?")
            elif unit in ("day", "week"):
                days = value * (7 if unit == "week" else 1)
                if start_date:
                    deadline = start_date + timedelta(days=days)
            elif start_date:
                try:
                    deadline = _add_months(start_date, value * (12 if unit == "year" else 1))
                    days = (deadline - start_date).days
                    notes.append("Calendar months/years are added to the recorded inquiry date; unavailable month-end days are clamped to that month's last day.")
                except (ValueError, OverflowError):
                    local_questions.append("What feasible delivery date should be used for this calendar duration?")
            else:
                local_questions.append("What recorded inquiry date should anchor the requested calendar months or years?")
        elif deadline:
            if start_date:
                days = (deadline - start_date).days
            else:
                local_questions.append("What recorded inquiry date should be used to calculate the days remaining to this deadline?")
        if days is not None and days < 1:
            local_questions.append("The stated deadline is today or in the past. What future delivery date should be used?")
            days = None
        if precision in ("approximate", "tentative"):
            local_questions.append("Is this an estimate/preference, or can the customer confirm a firm delivery deadline?")
            notes.append("The calculated calendar target is an estimate/preference, not an exact confirmed deadline.")
            days = None
        candidates.append({"kind":kind, "source_phrase":phrase, "original_text":phrase, "duration_value":value,
                           "unit":unit, "deadline":deadline, "precision":precision, "constraint":constraint,
                           "explicitly_confirmed":confirmed, "requested_days":days, "clarifications":local_questions})

    # Dates are parsed separately and never treated as duration numerals.
    for pattern in (_ISO_DATE, _MONTH_DATE, _AR_DATE):
        for match in pattern.finditer(normalized):
            month_text = match.group("month").lower()
            month = _MONTHS.get(month_text) or _AR_MONTHS.get(month_text)
            try:
                deadline = date(int(match.group("year")), month or int(month_text), int(match.group("day")))
                add(match, "date", deadline=deadline)
            except ValueError:
                add(match, "date", problem="What valid Gregorian delivery date did the customer intend?")
            occupied.append(match.span())
    for match in _NEXT_DAY.finditer(normalized):
        weekday = _WEEKDAYS[match.group("en").lower()] if match.group("en") else _AR_WEEKDAYS[match.group("ar")]
        deadline = start_date + timedelta(days=(weekday - start_date.weekday()) % 7 or 7) if start_date else None
        add(match, "relative", deadline=deadline, problem=None if start_date else "What recorded inquiry date should anchor 'next' weekday?")
        notes.append("Next weekday means its next strictly future occurrence in Saudi time, including seven days ahead when received on that weekday.")
    for match in _END_MONTH.finditer(normalized):
        deadline = None
        if start_date:
            next_month = _add_months(start_date.replace(day=1), 1)
            deadline = next_month.replace(day=calendar.monthrange(next_month.year, next_month.month)[1])
        add(match, "relative", deadline=deadline, problem=None if start_date else "What recorded inquiry date should anchor the end of next month?")
    for match in _DURATION.finditer(normalized):
        if any(a <= match.start() < b for a,b in occupied):
            continue
        unit_text = match.group("unit").lower()
        unit = _AR_UNITS.get(unit_text) or _DUALS.get(unit_text) or unit_text.rstrip("s")
        value = _number(match.group("amount"))
        prefix = normalized[max(0, match.start()-45):match.start()]
        ranged = re.search(rf"(?:\d+|{_WORDS})\s+(?:to|or|and)\s+$", prefix, re.I)
        problem = "Please confirm a single calendar delivery target; business/working days and ranges need clarification." if match.group("mode") and match.group("mode").lower() != "calendar" or ranged else None
        add(match, "duration", value=value, unit=unit, problem=problem)
        occupied.append(match.span())
    for match in _AR_SINGLE.finditer(normalized):
        if any(a <= match.start() < b or match.start() <= a < match.end() for a,b in occupied):
            continue
        unit_text = match.group("unit")
        add(match, "duration", value=2 if unit_text in _DUALS else 1, unit=_DUALS.get(unit_text) or _AR_UNITS[unit_text])
    urgency = _URGENCY.search(normalized)
    result = Timeline(reference_at=reference, notes=list(dict.fromkeys(notes)))
    if candidates:
        result = Timeline(**candidates[0], reference_at=reference, notes=result.notes)
        identities = {("days", c["requested_days"]) if c["requested_days"] is not None else (c["kind"], c["duration_value"], c["unit"], c["deadline"], c["precision"]) for c in candidates}
        if len(identities) > 1:
            questions.append("Conflicting delivery timelines were provided. Which single target should be used?")
            result.original_text = " | ".join(c["source_phrase"] for c in candidates)
            result.requested_days = None
        questions.extend(q for c in candidates for q in c["clarifications"])
    elif urgency:
        phrase = text[urgency.start():urgency.end()]
        result = Timeline(kind="urgency", original_text=phrase, source_phrase=phrase, constraint="urgency", reference_at=reference)
        questions.append("What specific delivery date or duration does ASAP/urgent mean for this customer?")
    else:
        result.source_phrase = result.original_text = source_hint or ""
        questions.append("What delivery duration or unambiguous Gregorian deadline should be used?")
    if explicit_days is not None:
        if isinstance(explicit_days, bool) or not isinstance(explicit_days, int) or explicit_days < 1:
            raise ValueError("requested_days must be a positive integer")
        valid_source = explicit_source is None or bool(explicit_source and explicit_source in text and any(explicit_source in c["source_phrase"] for c in candidates))
        verified_explicit = any(explicit_source and explicit_source in c["source_phrase"] and c["requested_days"] == explicit_days and c["precision"] == "exact" and not c["clarifications"] for c in candidates)
        if not valid_source:
            questions.append("The model's requested_days does not identify a verifiable delivery expression. Please confirm the target.")
        elif explicit_source is not None and not verified_explicit:
            questions.append("Extracted requested_days conflicts with the customer timeline. Please confirm the target.")
            # A numeral from a calendar date or week count must not replace the
            # correctly derived day window. Keep the deterministic fact instead.
        elif verified_explicit:
            result.requested_days = explicit_days  # Preserve a valid field even when another phrase conflicts.
        elif explicit_source is None:
            if result.requested_days is not None and result.requested_days != explicit_days:
                questions.append("The structured requested_days conflicts with the customer timeline. Please confirm the target.")
            result.requested_days = explicit_days
            if not candidates and not urgency and not source_hint:
                questions = []
                result.kind, result.precision, result.unit, result.duration_value = "duration", "exact", "day", explicit_days
                result.notes.append("Explicit structured requested_days retained; no customer source phrase was provided.")
    if re.search(r"Hijri|هجري|هجرية", normalized, re.I):
        questions.append("What Gregorian delivery date corresponds to the stated Hijri deadline?")
        result.requested_days = None
    result.clarifications = list(dict.fromkeys(questions))
    return result


def normalized_model_timeline(text: str, evidence, reference_at=None, source_hint=None) -> Timeline:
    """Clear customer evidence outranks an optional model interpretation.

    Preserve structured-field conflict checking in normalize_timeline, but do not
    mistake a model's week/day conversion error for a customer contradiction.
    Ambiguous or unsupported text can never be resolved by model arithmetic.
    """
    usable_hint = source_hint if source_hint and source_hint in text else None
    result = normalize_timeline(text, reference_at=reference_at, source_hint=usable_hint)
    if source_hint and not usable_hint:
        result.notes.append("Ignored model timeline source not found verbatim in the inquiry.")
    if evidence is not None:
        try:
            value = Decimal(evidence.value)
        except InvalidOperation:
            value = None
        consistent = value is not None and value.is_finite() and result.requested_days is not None and value == result.requested_days and bool(evidence.source and evidence.source in text and evidence.source in result.source_phrase)
        if not consistent:
            result.notes.append("Ignored inconsistent model requested_days; the deterministic customer timeline and any clarification requirements are retained.")
    return result
