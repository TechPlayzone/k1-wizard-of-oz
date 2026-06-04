import os

files = [
    'backend/llm_router.py',
    'backend/session_manager.py',
    'backend/k1_handler.py',
    'backend/tts.py',
    'backend/stt.py',
    'backend/app.py',
    'backend/config.py',
]

replacements = [
    ('str | None',              'object'),
    ('list[dict]',              'list'),
    ('list[str]',               'list'),
    ('list[dict] | None',       'object'),
    ('float | None',            'object'),
    ('tuple[str, str | None]',  'tuple'),
    ('str | None = None',       'object = None'),
    ('-> list:',                '-> list'),
    ('-> str | None:',          '-> object'),
]

for f in files:
    if not os.path.exists(f):
        print(f'Skipping (not found): {f}')
        continue
    txt = open(f, encoding='utf-8').read()
    for old, new in replacements:
        txt = txt.replace(old, new)
    open(f, 'w', encoding='utf-8').write(txt)
    print(f'Fixed: {f}')

print('\nDone. Run: python backend/app.py')
