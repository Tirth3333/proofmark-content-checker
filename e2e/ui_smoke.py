"""Browser smoke test: loads the demo, analyzes, accepts two fixes, checks the revised text,
and saves screenshots at desktop, mobile and tablet widths.
Usage: python e2e/ui_smoke.py  (needs backend + frontend running; pip install playwright)
"""
import asyncio, sys
from playwright.async_api import async_playwright
import os
OUT=os.environ.get('SHOT_DIR','e2e/screenshots/'); os.makedirs(OUT, exist_ok=True)
BASE=os.environ.get('APP_URL','http://127.0.0.1:5173/')
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width':1440,'height':950})
        errs=[]
        pg.on('console', lambda m: errs.append(m.text) if m.type=='error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.route('**/fonts.g*/**', lambda r: r.abort())
        await pg.goto(BASE)
        await pg.wait_for_timeout(800)
        await pg.screenshot(path=OUT+'01-empty.png')
        await pg.get_by_role('button', name='Load demo article').click()
        await pg.screenshot(path=OUT+'02-demo.png')
        await pg.get_by_role('button', name='Analyze', exact=True).click()
        await pg.wait_for_selector('.summary')
        await pg.wait_for_timeout(500)
        await pg.screenshot(path=OUT+'03-review.png')
        # select a filler card and accept it
        card = pg.locator('.card', has_text='Filler language').first
        await card.locator('.card-head').click()
        await card.get_by_role('button', name='Accept change').click()
        await pg.locator('.card', has_text='Use preferred terminology').first.get_by_role('button', name='Accept change').click()
        await pg.screenshot(path=OUT+'04-accepted.png')
        await pg.get_by_role('tab', name='Compare (2)').click()
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT+'05-compare.png')
        rev = await pg.get_by_test_id('revised-text').inner_text()
        assert rev.startswith('# How to Choose Project Management Software for a Small Team\n\nChoosing project management software'), rev[:150]
        assert 'customers' in rev
        print('revised text OK')
        await pg.set_viewport_size({'width':390,'height':844})
        await pg.get_by_role('tab', name='Review').click()
        await pg.screenshot(path=OUT+'06-mobile.png', full_page=False)
        await pg.set_viewport_size({'width':820,'height':1100})
        await pg.screenshot(path=OUT+'07-tablet.png')
        errs = [e for e in errs if 'ERR_FAILED' not in e]  # blocked web fonts in sandboxes
        assert not errs, errs
        print('no console errors')
        await b.close()
asyncio.run(main())
