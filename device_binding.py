"""Conservative physical identity matching, never names or serial alone on conflict."""
def resolve_hid(rows, selected=None):
    rows=list(rows)
    if selected is None:return rows[0] if len(rows)==1 else None
    matches=[]
    for row in rows:
        if any(selected.get(k) and row.get(k) and selected[k]!=row[k]
               for k in ('serial_number','container_id')):continue
        if (selected.get('container_id') and selected['container_id']==row.get('container_id') or
            selected.get('serial_number') and selected['serial_number']==row.get('serial_number') or
            selected.get('path')==row.get('path')):matches.append(row)
    return matches[0] if len(matches)==1 else None

def select_output(rows, hid, name=None, previous=None):
    # A unique name is not evidence that HID and audio belong to the same dongle.
    candidates=[r for r in rows if r.get('maxOutputChannels',0)>=4 and
                hid.get('container_id') and r.get('container_id')==hid['container_id']]
    if name is not None and previous is None:candidates=[r for r in candidates if r['name']==name]
    if previous and previous.get('container_id')!=hid.get('container_id'):return None
    return candidates[0] if len(candidates)==1 else None
