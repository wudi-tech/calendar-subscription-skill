"""Build a deterministic, timed-event iCalendar subscription feed (stdlib only)."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import uuid


def text_value(value, field, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f'{field} must be a nonempty string' if required else f'{field} must be a string')
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    if any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise ValueError(f'{field} contains control characters')
    return value


def escape(value):
    return value.replace('\\', '\\\\').replace('\n', '\\n').replace(';', '\\;').replace(',', '\\,')


def timestamp(value, field):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field} must be an ISO datetime with a UTC offset') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f'{field} requires a UTC offset, for example +08:00')
    if result.microsecond:
        raise ValueError(f'{field} must use whole seconds')
    return result.astimezone(timezone.utc)


def format_utc(value):
    return value.strftime('%Y%m%dT%H%M%SZ')


def fold(line):
    chunks, current = [], ''
    for char in line:
        if len((current + char).encode('utf-8')) > 75:
            chunks.append(current)
            current = ' '  # The continuation space counts toward the 75-octet limit.
        current += char
    chunks.append(current)
    return '\r\n'.join(chunks)


def build_feed(data):
    if not isinstance(data, dict):
        raise ValueError('Input must be a JSON object')
    unknown = set(data) - {'feed_id', 'calendar_name', 'events'}
    if unknown:
        raise ValueError(f'Unsupported feed fields: {", ".join(sorted(unknown))}')
    feed_id = text_value(data.get('feed_id'), 'feed_id', required=True)
    name = text_value(data.get('calendar_name'), 'calendar_name', required=True)
    events = data.get('events')
    if not isinstance(events, list):
        raise ValueError('events must be a list')
    lines = ['BEGIN:VCALENDAR', 'VERSION:2.0',
             'PRODID:-//Calendar Subscription Skill//EN', 'CALSCALE:GREGORIAN',
             f'X-WR-CALNAME:{escape(name)}']
    seen = set()
    normalized = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('Each event must be an object')
        unknown = set(event) - {'id', 'title', 'start', 'end', 'updated_at', 'sequence',
                                'status', 'alarm_minutes', 'description', 'location'}
        if unknown:
            raise ValueError(f'Unsupported event fields: {", ".join(sorted(unknown))}')
        event_id = text_value(event.get('id'), 'id', required=True)
        if event_id in seen:
            raise ValueError(f'Duplicate event id: {event_id}')
        seen.add(event_id)
        title = text_value(event.get('title'), 'title', required=True)
        start, end = (timestamp(event.get(key), key) for key in ('start', 'end'))
        if end <= start:
            raise ValueError(f'Event {event_id}: end must be later than start')
        modified = timestamp(event.get('updated_at'), 'updated_at')
        sequence = event.get('sequence', 0)
        if type(sequence) is not int or sequence < 0 or sequence > 2147483647:
            raise ValueError('sequence must be an integer between 0 and 2147483647')
        status = event.get('status', 'CONFIRMED')
        if status not in ('CONFIRMED', 'TENTATIVE', 'CANCELLED'):
            raise ValueError('status must be CONFIRMED, TENTATIVE or CANCELLED')
        alarm = event.get('alarm_minutes')
        if alarm is not None and (type(alarm) is not int or not 1 <= alarm <= 40320):
            raise ValueError('alarm_minutes must be an integer between 1 and 40320, or null')
        # Length-safe encoding avoids ambiguity when feed_id/id contain punctuation.
        identity = json.dumps([feed_id, event_id], ensure_ascii=False, separators=(',', ':'))
        uid = f'{uuid.uuid5(uuid.NAMESPACE_URL, identity)}@calendar-subscription.invalid'
        block = ['BEGIN:VEVENT', f'UID:{uid}', f'DTSTAMP:{format_utc(modified)}',
                 f'LAST-MODIFIED:{format_utc(modified)}', f'SEQUENCE:{sequence}',
                 f'DTSTART:{format_utc(start)}', f'DTEND:{format_utc(end)}',
                 f'SUMMARY:{escape(title)}', f'STATUS:{status}']
        for key in ('description', 'location'):
            if key in event:
                block.append(f'{key.upper()}:{escape(text_value(event[key], key))}')
        if alarm is not None and status != 'CANCELLED':
            block.extend(['BEGIN:VALARM', 'ACTION:DISPLAY', f'TRIGGER:-PT{alarm}M',
                          f'DESCRIPTION:{escape(title)}', 'END:VALARM'])
        block.append('END:VEVENT')
        normalized.append((start, event_id, block))
    for _, _, block in sorted(normalized):
        lines.extend(block)
    lines.append('END:VCALENDAR')
    return ('\r\n'.join(fold(line) for line in lines) + '\r\n').encode('utf-8')


def write_if_changed(output, content):
    if output.exists() and output.read_bytes() == content:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
        os.replace(temporary, output)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Structured event JSON')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path, help='Destination ICS; replaced only if changed')
    mode.add_argument('--check', action='store_true', help='Validate without writing')
    args = parser.parse_args()
    try:
        if args.output and args.input.resolve() == args.output.resolve():
            raise ValueError('Input and output must be different files')
        data = json.loads(args.input.read_text(encoding='utf-8-sig'))
        content = build_feed(data)
        if args.check:
            print(f'Valid: {len(data["events"])} events')
        else:
            changed = write_if_changed(args.output, content)
            print(f'{"Updated" if changed else "Unchanged"}: {args.output}')
    except (OSError, ValueError, OverflowError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
