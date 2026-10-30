"""Merge independently owned JSON and existing ICS sources into one subscription."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import json
from pathlib import Path, PureWindowsPath
import re

try:
    from icalendar import Calendar
except ImportError:
    raise SystemExit('Multi-source mode needs icalendar; install the supplied requirements-merge.txt with your Python interpreter.') from None

from build_feed import build_feed, text_value, write_if_changed


def read_manifest(path):
    path = Path(path).resolve()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or set(data) - {'calendar_name', 'sources'}:
        raise ValueError('Manifest must contain only calendar_name and sources')
    text_value(data.get('calendar_name'), 'calendar_name', required=True)
    if not isinstance(data.get('sources'), list) or not data['sources']:
        raise ValueError('sources must be a nonempty list')
    sources, ids, paths = [], set(), set()
    for source in data['sources']:
        if not isinstance(source, dict) or set(source) - {'id', 'path', 'format', 'enabled'}:
            raise ValueError('Each source needs id, path, format and optional enabled')
        source_id = text_value(source.get('id'), 'source.id', required=True)
        if source_id in ids:
            raise ValueError(f'Duplicate source id: {source_id}')
        ids.add(source_id)
        enabled = source.get('enabled', True)
        if type(enabled) is not bool:
            raise ValueError('source.enabled must be true or false')
        if not enabled:
            continue
        relative = text_value(source.get('path'), 'source.path', required=True)
        if Path(relative).is_absolute() or PureWindowsPath(relative).is_absolute() or re.match(r'^[a-zA-Z]+:', relative):
            raise ValueError('Source paths must be relative files inside the manifest directory')
        resolved = (path.parent / relative).resolve()
        if not resolved.is_relative_to(path.parent) or resolved == path:
            raise ValueError(f'Source escapes manifest root or points to manifest: {relative}')
        if resolved in paths:
            raise ValueError(f'Duplicate source path: {relative}')
        paths.add(resolved)
        if source.get('format') not in ('json', 'ics'):
            raise ValueError('source.format must be json or ics')
        sources.append({**source, 'resolved': resolved})
    if not sources:
        raise ValueError('No enabled sources')
    return data, sorted(sources, key=lambda item: item['id'])


def event_identity(event):
    uid = event.get('UID')
    if uid is None or isinstance(uid, list) or not str(uid).strip():
        raise ValueError('Every event must have exactly one nonempty UID')
    recurrence = event.get('RECURRENCE-ID')
    if isinstance(recurrence, list):
        raise ValueError('An event cannot have multiple RECURRENCE-ID values')
    if recurrence is None:
        occurrence = ''
    else:
        value = recurrence.dt
        if isinstance(value, datetime) and value.utcoffset() is not None:
            value = value.astimezone(timezone.utc)
        occurrence = value.isoformat()
    return str(uid), occurrence


def build_calendar(manifest_path, *, destination=None):
    manifest, sources = read_manifest(manifest_path)
    if destination is not None:
        output = Path(destination).resolve()
        protected = {Path(manifest_path).resolve(), *(source['resolved'] for source in sources)}
        if output in protected:
            raise ValueError('Output cannot overwrite the manifest or a source')
    result = Calendar()
    result.add('PRODID', '-//Calendar Subscription Skill//Multi-source//EN')
    result.add('VERSION', '2.0')
    result.add('CALSCALE', 'GREGORIAN')
    result.add('X-WR-CALNAME', manifest['calendar_name'])
    events, timezones, namespaces = {}, {}, set()
    for source in sources:
        payload = source['resolved'].read_bytes()
        if source['format'] == 'json':
            data = json.loads(payload.decode('utf-8-sig'))
            payload = build_feed(data)
            namespace = data['feed_id']
            if namespace in namespaces:
                raise ValueError(f'JSON sources must have distinct permanent feed_id values: {namespace}')
            namespaces.add(namespace)
        # Legacy Windows text-mode writers could turn CRLF into CRCRLF.
        # Normalize only the line terminators while leaving the source file untouched.
        payload = re.sub(rb'\r+\n', b'\r\n', payload)
        try:
            calendar = Calendar.from_ical(payload)
        except (ValueError, TypeError) as error:
            raise ValueError(f'Invalid ICS in source {source["id"]}: {error}') from error
        if calendar.name != 'VCALENDAR' or str(calendar.get('VERSION', '')) != '2.0':
            raise ValueError(f'Source {source["id"]} is not an iCalendar 2.0 calendar')
        if any(component.errors for component in calendar.walk()):
            raise ValueError(f'Source {source["id"]} contains invalid calendar properties')
        for component in calendar.subcomponents:
            if component.name == 'VTIMEZONE':
                tzid = str(component.get('TZID', ''))
                if not tzid:
                    raise ValueError('VTIMEZONE needs TZID')
                serialized = component.to_ical()
                if tzid in timezones and timezones[tzid].to_ical() != serialized:
                    raise ValueError(f'Conflicting VTIMEZONE definitions: {tzid}')
                timezones[tzid] = copy.deepcopy(component)
            elif component.name == 'VEVENT':
                identity = event_identity(component)
                if identity in events:
                    raise ValueError(f'Duplicate event UID/occurrence across sources: {identity}')
                events[identity] = copy.deepcopy(component)
            else:
                raise ValueError(f'Unsupported top-level component: {component.name}; source was not dropped')
    if not events:
        raise ValueError('Refusing an empty merged calendar; review the source configuration')
    for tzid in sorted(timezones):
        result.add_component(timezones[tzid])
    for identity in sorted(events):
        result.add_component(events[identity])
    return result.to_ical()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        content = build_calendar(args.manifest, destination=args.output)
        count = len(Calendar.from_ical(content).walk('VEVENT'))
        if args.check:
            print(f'Valid merged calendar: {count} event components')
        else:
            changed = write_if_changed(args.output, content)
            print(f'{"Updated" if changed else "Unchanged"}: {args.output} ({count} event components)')
    except (OSError, ValueError, TypeError, OverflowError) as error:
        parser.exit(1, f'Error: {error}\n')


if __name__ == '__main__':
    main()
