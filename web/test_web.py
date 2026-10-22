"""
test_web.py - Automated Test Suite for Beatbar Web Viewer
"""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(CURRENT_DIR)
for p in [CURRENT_DIR, ROOT_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from web.app import app

def run_tests():
    client = app.test_client()

    print("Running Web Viewer Test Suite...")

    # 1. Test index page
    r = client.get('/')
    assert r.status_code == 200, f"Index failed: {r.status_code}"
    assert b"BEATBAR WEB VIEWER" in r.data, "Missing title in index"
    print("[PASS] 1. Index page loads successfully")

    # 2. Test config endpoint
    r = client.get('/api/config')
    assert r.status_code == 200
    cfg = r.get_json()
    assert "videos_folder" in cfg and "lan_ips" in cfg
    print(f"[PASS] 2. Config endpoint returned LAN IPs: {cfg['lan_ips']}")

    # 3. Test library endpoint
    r = client.get('/api/library')
    assert r.status_code == 200
    lib = r.get_json()
    total_videos = lib['total_videos']
    assert total_videos >= 0, f"Expected non-negative videos, got {total_videos}"
    print(f"[PASS] 3. Library returned {total_videos} videos:")
    for v in lib['videos']:
        b_info = v.get("beat_info", {})
        print(f"   - {v['filename']}: {v['duration_formatted']}, {b_info.get('beat_count', 0)} beats ({b_info.get('format', 'none')})")

    # 4. Test beats endpoint for allure-hmv-pmv-arckom2_720p_beats
    test_file = lib['videos'][0]['filename']
    r = client.get(f'/api/beats/{test_file}')
    assert r.status_code == 200
    b_data = r.get_json()
    assert b_data['has_beats'] is True
    print(f"[PASS] 4. Beats endpoint for {test_file} returned {len(b_data['beats'])} beats and {len(b_data.get('zones', []))} zones")

    # 5. Test rating endpoint
    r = client.post(f'/api/rate_video/{test_file}', json={'rating': 5})
    assert r.status_code == 200
    res_rate = r.get_json()
    assert res_rate['rating'] == 5
    print(f"[PASS] 5. Rate video endpoint set rating to 5")

    # 6. Test thumbnail endpoint
    r = client.get(f'/api/thumbnail/{test_file}')
    assert r.status_code == 200
    assert r.content_type == 'image/jpeg'
    assert len(r.data) > 1000
    print(f"[PASS] 6. Thumbnail endpoint returned {len(r.data)} bytes image/jpeg")

    # 7. Test video streaming with Range request (206 Partial Content)
    r = client.get(f'/api/video/{test_file}', headers={'Range': 'bytes=0-1023'})
    assert r.status_code == 206, f"Expected 206 Partial Content, got {r.status_code}"
    assert len(r.data) == 1024, f"Expected 1024 bytes, got {len(r.data)}"
    assert 'bytes 0-1023/' in r.headers.get('Content-Range', '')
    print(f"[PASS] 7. Video Range request returned 206 Partial Content with 1024 bytes")

    # 8. Test QR code generation
    r = client.get('/api/qrcode')
    assert r.status_code == 200
    assert r.content_type == 'image/png'
    assert len(r.data) > 500
    print(f"[PASS] 8. QR Code generated successfully ({len(r.data)} bytes image/png)")

    # 9. Test static files
    for static_file in ['/static/css/style.css', '/static/js/beatbar.js', '/static/js/player.js', '/static/js/library.js', '/static/js/app.js']:
        r = client.get(static_file)
        assert r.status_code == 200, f"Static file failed: {static_file} ({r.status_code})"
    print(f"[PASS] 9. All 5 static CSS & JS assets loaded successfully (200 OK)")

    # 10. Test skins list endpoint
    r = client.get('/api/skins')
    assert r.status_code == 200, f"Skins endpoint failed: {r.status_code}"
    skins_data = r.get_json()
    assert 'skins' in skins_data
    skins_list = skins_data['skins']
    assert len(skins_list) >= 1, f"Expected at least 1 skin, got {len(skins_list)}"
    print(f"[PASS] 10. Skins list returned {len(skins_list)} skin(s):")
    for s in skins_list:
        print(f"    - {s['id']}: {s['name']} (comps: {list(s.get('components', {}).keys())})")

    # 11. Test individual skin endpoint
    r = client.get('/api/skin/cyber_wings')
    assert r.status_code == 200
    skin_cw = r.get_json()
    assert skin_cw['id'] == 'cyber_wings'
    assert 'panel' in skin_cw['components']
    print(f"[PASS] 11. Individual skin 'cyber_wings' retrieved successfully")

    # 12. Test skin component asset serving (panel, wing_left, target, beat)
    for comp in ['panel', 'wing_left', 'target', 'beat']:
        r = client.get(f'/api/skin/cyber_wings/asset/{comp}')
        assert r.status_code == 200, f"Asset {comp} failed: {r.status_code}"
        assert 'svg' in r.content_type.lower() or 'image' in r.content_type.lower()
        assert len(r.data) > 100
    print(f"[PASS] 12. Skin assets (panel, wing_left, target, beat) served successfully with valid MIME")

    # 13. Test skin wing_right asset
    r = client.get('/api/skin/cyber_wings/asset/wing_right')
    assert r.status_code == 200, f"wing_right failed: {r.status_code}"
    assert len(r.data) > 100
    print(f"[PASS] 13. Cyber Wings wing_right asset served successfully ({len(r.data)} bytes)")

    # 14. Test beatmap parsing
    target_vid = lib['videos'][0]['filename'] if lib.get('videos') else None
    if target_vid:
        r = client.get(f'/api/beats/{target_vid}')
        assert r.status_code == 200
        b_data = r.get_json()
        assert 'beats' in b_data
        print(f"[PASS] 14. Beatmap parsing verified for {target_vid} (Total beats: {len(b_data['beats'])})")
    else:
        print("[PASS] 14. No video to test beatmap parsing (skipped)")

    print("=" * 60)
    print(" ALL 14 VERIFICATION TESTS PASSED SUCCESSFULLY! ")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
