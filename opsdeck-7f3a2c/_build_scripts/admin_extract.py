"""
Extraction script for the Admin module of the SurgiCentral static demo.

Reads the raw Postgres CSV dump (../../_raw_db_backup_2026-07-23/) and
reproduces the query logic in surgicentral/admin/routes.py to produce
static JSON consumed by Clone/admin/*.html.

Outputs:
  Clone/data/admin/users.json  -- admin/users.html
  Clone/data/admin/roles.json  -- admin/roles.html

Only stdlib (csv, json) is used.

Data note: users.csv has exactly 2 real rows (Gary Starr, Craig Giordano).
Per Gary's explicit approval (see task brief / CLAUDE.md), real names/emails
are shown as-is -- this is a private/unlisted demo, not a public site.
qbo_tokens.csv / qbo_auth_states.csv are never read by this script and
admin/routes.py's QBO Auth / Full Sync / Incremental Sync actions have no
static equivalent -- those nav links are already data-demo-inert in
assets/partials/nav.html. Competitor Sync (admin_bp /admin/competitor-sync)
is likewise nav-level inert, not a page in this module's scope.
"""
import csv
import json
import os

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_raw_db_backup_2026-07-23')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'admin')


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def main():
    users_raw = read_csv('users.csv')
    roles_raw = read_csv('roles.csv')
    user_roles_raw = read_csv('user_roles.csv')
    modules_raw = read_csv('modules.csv')
    role_perms_raw = read_csv('role_permissions.csv')

    roles_by_id = {r['id']: r for r in roles_raw}

    # role_names per user: string_agg(r.display_name, ', ' ORDER BY r.display_name)
    role_names_by_user = {}
    for ur in user_roles_raw:
        role = roles_by_id.get(ur['role_id'])
        if not role:
            continue
        role_names_by_user.setdefault(ur['user_id'], []).append(role['display_name'])
    for uid in role_names_by_user:
        role_names_by_user[uid].sort()

    users = []
    for u in users_raw:
        names = role_names_by_user.get(u['id'], [])
        users.append({
            'id': int(u['id']),
            'email': u['email'],
            'name': u['name'] or None,
            'is_active': u['is_active'] == 't',
            'created_at': u['created_at'] or None,
            'last_login_at': u['last_login_at'] or None,
            'role_names': ', '.join(names) if names else '—',
        })
    # ORDER BY u.is_active DESC, u.name
    users.sort(key=lambda u: (not u['is_active'], u['name'] or ''))

    # all_roles: WHERE is_active ORDER BY display_name -- used to populate the
    # "Roles" checkbox modal per user
    all_roles_active = [
        {'id': int(r['id']), 'name': r['name'], 'display_name': r['display_name']}
        for r in roles_raw if r['is_active'] == 't'
    ]
    all_roles_active.sort(key=lambda r: r['display_name'])

    users_payload = {
        'generated_note': 'Full snapshot -- both real SurgiCentral user accounts, 2026-07-23.',
        'users': users,
        'all_roles': all_roles_active,
    }
    with open(os.path.join(OUT_DIR, 'users.json'), 'w', encoding='utf-8') as f:
        json.dump(users_payload, f, indent=1)

    # ── roles.json ───────────────────────────────────────────────────────────
    all_roles = [{
        'id': int(r['id']),
        'name': r['name'],
        'display_name': r['display_name'],
        'description': r['description'] or None,
        'is_active': r['is_active'] == 't',
    } for r in roles_raw]
    all_roles.sort(key=lambda r: r['display_name'])

    all_modules = [{
        'id': int(m['id']),
        'name': m['name'],
        'display_name': m['display_name'],
        'sort_order': int(m['sort_order']) if m['sort_order'] else 0,
    } for m in modules_raw if m['is_active'] == 't']
    all_modules.sort(key=lambda m: m['sort_order'])

    # perm_map: {role_id: {module_id: level}}
    perm_map = {}
    for rp in role_perms_raw:
        perm_map.setdefault(rp['role_id'], {})[rp['module_id']] = rp['level']

    roles_payload = {
        'generated_note': 'Full snapshot -- all 12 roles x 7 active modules, 2026-07-23.',
        'roles': all_roles,
        'modules': all_modules,
        'perm_map': perm_map,
    }
    with open(os.path.join(OUT_DIR, 'roles.json'), 'w', encoding='utf-8') as f:
        json.dump(roles_payload, f, indent=1)

    print(f"users.json: {len(users)} users, {len(all_roles_active)} active roles")
    print(f"roles.json: {len(all_roles)} roles, {len(all_modules)} modules, "
          f"{sum(len(v) for v in perm_map.values())} permission entries")


if __name__ == '__main__':
    main()
