"""회차 배경 이미지 일괄 생성 — Codex CLI의 내장 image_gen을 쓴다.

OpenAI Images API를 직접 쓰면 과금되지만, `codex exec`는 ChatGPT 구독 쿼터로
같은 모델을 쓴다. 대신 **쿼터가 실재한다** — 한 번에 8장쯤에서 막힌 적이 있다.
그래서 이 스크립트는 (1) 이미 있는 파일은 건너뛰고 (2) 실패하면 거기서 멈춘다.
다음 날 다시 돌리면 이어서 채운다.

사용: python3 scripts/gen_images.py [회차접두어 ...]      예) gen_images.py kim nam

엔진 순서(2026-09-26 사용자 지시): **① codex → ② codex 쿼터가 끝나 실패하면 로컬 SDXL**
⚠️ 같은 날 로컬 SDXL 을 삭제했다(디스크 확보). 설치돼 있지 않으면 ②를 건너뛰고 멈춘다 — 한도 해제 후 재실행.
(`~/Desktop/kim/ssul/pipeline/gen_local.py`, RealVisXL + Lightning 8스텝, 768×480 생성 → 1024×768 크롭).
mflux(Z-Image-Turbo)는 느려서 삭제했다(2026-09-26). SDXL 은 얼굴 정면이 무너지기 쉬워 네거티브로 막아 뒀다.
"""
import os
import subprocess
import sys

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT = os.path.join(BASE, "output/images")

# 전 회차 공통 — PRD 5항. 사람 얼굴이 식별되면 실존 인물 오인 소지가 생긴다.
STYLE = ("Documentary still-photograph look, aged monochrome/sepia archival photo, "
         "soft film grain, muted contrast, landscape orientation 4:3. "
         "No identifiable faces (people only as distant figures, silhouettes, or from behind). "
         "No text, no captions, no watermarks, no modern objects.")

# v3 컬러 회차(PRD v3 — 2026-09-24 사용자 지시 "사진은 컬러로").
# 여기 적힌 접두어로 시작하는 장면은 세피아 대신 이 스타일로 뽑는다.
STYLE_COLOR = ("Cinematic documentary still in natural, slightly muted color, as if shot on 35mm film: "
               "soft film grain, gentle contrast, realistic light, landscape orientation 4:3. "
               "No identifiable faces (people only as distant figures, silhouettes, or from behind). "
               "No text, no captions, no watermarks, no modern objects.")
COLOR_PREFIXES = ("chu_", "yun_", "sam_", "nsj_")

# v3 삽화 회차 (2026-09-25 사용자 지시 — "장면에 이 사람을 등장시켜라, 얼굴 정면은 쓰지 말고 실사보다 그림체로").
# 주인공 인상착의를 CHARACTER에 고정해 모든 컷에 붙인다 — 컷마다 다른 사람처럼 보이지 않게.
STYLE_ILLUST = ("Painted historical illustration, like a Korean graphic-novel panel: textured brush strokes, "
                "muted warm palette, cinematic lighting, landscape orientation 4:3. "
                "The main character appears in the scene but NEVER with a frontal face — show him from behind, "
                "in side silhouette turned away, in shadow, or only his hands. Other people only as distant figures. "
                "No text, no captions, no watermarks, no modern objects.")
ILLUST = {           # 접두어 → 주인공 인상착의
    "lyj_": ("a slim Korean scholar in his fifties (1940s), short dark hair parted to the side, round black-rimmed glasses, "
             "clean-shaven, wearing a grey traditional Korean hanbok with a white collar band. Always the same man."),
}

SCENES = {
 # 6화 김익상 — 1921 조선총독부 투탄
 "kim_01_hall":   "A 1920s colonial government office corridor in Korea right after a bomb blast: shattered window glass on the floor, drifting smoke, an overturned wooden chair, scattered papers. No people.",
 "kim_02_toolbag":    "A worn 1920s electrician's canvas tool bag on a stone floor, with pliers and a roll of cloth insulating tape spilling out. Close view. No people.",
 "kim_03_wires":  "An old electrical distribution board on a plaster wall with bundles of cloth-wrapped wires hanging loose, 1920s. No people.",
 "kim_04_stairs": "An empty stone stair landing inside a 1920s government building, tall window, dust in the light shaft. No people.",
 "kim_05_street": "A distant wide view of a 1920s Korean colonial city street, low tiled roofs and a few utility poles, seen from far away. Figures only as tiny distant silhouettes.",
 "kim_06_pier":  "A 1920s Shanghai wharf in mist: a moored steamship hull, thick mooring ropes on bollards, wet stone quay. No people.",
 "kim_07_dock":   "An empty wooden defendant's dock in a 1920s courtroom, plain rail and bench, shuttered window behind. No people.",
 "kim_08_gate":   "A heavy iron prison gate seen from outside, brick wall, 1930s. No people.",
 "kim_09_river":  "A wide river at dawn under heavy fog, faint far bank, still water. No people.",

 # 7화 남자현 — 1933 하얼빈
 "nam_01_street": "A 1930s Harbin street in winter seen from far away: snow on the ground, a tram and low European-style buildings, figures only as tiny distant silhouettes.",
 "nam_02_bundle": "An old cloth bojagi bundle and a coarse hemp sack resting on a wooden floor. Close view. No people.",
 "nam_03_flag":  "Flags on poles in front of a 1930s government building, seen from a distance, overcast sky. No people.",
 "nam_04_alley":  "A narrow snow-covered alley between brick walls in 1930s Manchuria, footprints in the snow. No people.",
 "nam_05_blood":  "A piece of white cloth on a wooden table with a dark stain spreading on it, and an old worn writing brush beside it. Close view. No people.",
 "nam_06_hanbok": "A woman's plain white Korean hanbok jeogori hanging on a wall hook in a bare room. No people.",
 "nam_07_school": "A small wooden schoolhouse alone on the wide Manchurian plain, low fence, bare trees. No people.",
 "nam_08_cell": "A narrow barred window high on a cell wall, faint light falling on a stone floor. No people.",
 "nam_09_grave":  "Snow-covered gravestones in a foreign cemetery, bare branches, winter light. No people.",

 # 8화 강기동 — 의병
 "kang8_01_post":  "A small Japanese military police outpost building in rural Korea, around 1909: low wooden structure, plank fence, dirt yard. No people.",
 "kang8_02_cap":   "An old military-style peaked cap hanging on a nail on a plank wall, dim interior. Close view. No people.",
 "kang8_03_cell":  "Dark wooden bars of a village jail cell, faint light through them, earthen floor. No people.",
 "kang8_04_lamp":  "An oil lamp burning on a night-duty desk with a ledger and inkstone, dark room, 1900s. No people.",
 "kang8_05_rack":  "An empty wooden rifle rack against a plank wall of an armory, dust on the shelf. No people.",
 "kang8_06_uniform": "A dark high-collared uniform tunic hanging alone on a wall, empty, dim room. No people.",
 "kang8_07_mountain": "A winter mountain trail and bare ridgelines in Korea, snow patches, low cloud. No people.",
 "kang8_08_port":  "Wonsan harbor around 1910: wooden fishing boats moored at a stone pier, distant hills. No people.",
 "kang8_09_field":  "An empty military parade ground of bare packed earth, a low wall and a single bare tree at the edge, overcast. No people.",

 # 9화 스코필드 — 1919 제암리
 "sch_01_ruins":   "The burnt ruins of a small rural Korean church in 1919: charred timber posts, collapsed roof beams, ash on the ground, thin smoke still rising. No people.",
 "sch_02_bicycle": "An old bicycle from the 1910s leaning alone on a dirt country road, bare trees behind. No people.",
 "sch_03_camera":  "A 1910s folding bellows camera on a wooden table with glass photographic plates beside it. Close view. No people.",
 "sch_04_crowd":   "A very distant wide view of a large crowd filling a Korean city street in 1919, seen from far above; people only as an indistinct mass, no faces.",
 "sch_05_newspaper":   "An English-language newspaper page on a desk next to an old typewriter, 1919. Text unreadable and blurred. No people.",
 "sch_06_lab":     "An old laboratory bench with a brass microscope, glass petri dishes and specimen jars, 1910s. No people.",
 "sch_07_classroom":   "An empty medical school lecture room with wooden benches and a blackboard, 1910s. No people.",
 "sch_08_medal":   "A medal resting in an open velvet presentation case. Close view. No people.",
 "sch_09_grave":   "Rows of low uniform gravestones in a national cemetery in winter, seen from a distance, bare trees. No people.",

 # 10화 이육사 — 대구형무소·시
 "yuk_01_cell":    "A prison corridor of the 1920s: a heavy riveted iron door in a plaster wall, and an old worn enamel number plate fixed beside it. Numbers weathered and unreadable. No people.",
 "yuk_02_desk":    "An old sheet of Korean manuscript paper with ruled squares on a low wooden desk, a fountain pen and an ink stone beside it. Text unreadable. No people.",
 "yuk_03_bank":    "A distant view of a 1920s Western-style bank building of grey stone in a colonial Korean town, arched windows, empty street in front. No people.",
 "yuk_04_leaflet": "A night alley wall in a 1930s Korean town with torn printed handbills pasted on it and loose sheets of paper scattered on the ground. Text unreadable. No people.",
 "yuk_05_drill":   "A bare packed-earth drill ground in southern China, a low brick wall and bamboo behind it, 1930s, overcast. No people.",
 "yuk_06_brush":   "A calligraphy brush and ink stone on a sheet of paper with half-written strokes. Close view, characters indistinct and unreadable. No people.",
 "yuk_07_vineyard": "A summer grape arbor with heavy vines and ripening bunches of grapes hanging under the leaves. Close view. No people.",
 "yuk_08_station": "A 1940s railway platform with a steam locomotive standing at it, seen from far away, overcast sky. No people.",
 "yuk_09_field":   "A vast empty plain under falling snow, a bare distant horizon line, no trees. No people.",

 # 11화 조명하 — 1928 대만 타이중
 "cho_01_street":  "A street in Taichung, Taiwan in the late 1920s: palm trees along a paved road and a Japanese colonial government building, empty road. No people.",
 "cho_02_blade":   "A short dagger lying alone on a worn wooden table. Close view. No people.",
 "cho_03_crowd":   "A very distant wide view of a welcoming crowd lining a colonial-era street, seen from far away; people only as an indistinct mass, no faces.",
 "cho_04_shop":    "The interior of a 1920s Taiwanese shop: wooden display shelves and glass jars, dim light. No people.",
 "cho_05_factory": "A 1920s Japanese factory workshop: workbenches, belt-driven machines and a grimy window. No people.",
 "cho_06_gate":    "The front gate and stone pillars of a Japanese colonial government building, seen from a distance. No people.",
 "cho_07_yard":    "A bare earth yard with a low wall and bamboo in southern Taiwan, overcast. No people.",
 "cho_08_prison":  "A 1920s prison corridor with iron doors and a high barred window. No people.",
 "cho_09_sea":     "Waves of a strait and a far horizon under an overcast sky. No people.",
 "cho_10_school":  "An empty lecture room of a 1920s Japanese commercial school: rows of wooden desks, a blackboard and tall windows. No people.",

 # 12화 권기옥 — 1925 윈난항공학교·중국 공군
 # ⚠️ 마지막 컷은 실제 초상(커먼즈 PD)이므로 여기서 생성하지 않는다.
 "kwon_01_airfield": "A dirt airfield in southern China in the 1920s seen from far away: a single biplane parked on bare packed earth, low hills behind, hazy sky. No people.",
 "kwon_02_goggles":  "A pair of worn aviator goggles and a leather flying helmet lying on a wooden table. Close view. No people.",
 "kwon_03_hangar":   "The side view of a biplane standing inside an open hangar, morning light falling through the doorway onto the earth floor. No people.",
 "kwon_04_roster":   "An old paper roster sheet and a wooden seal stamp on a plain desk, 1920s. Close view, handwriting illegible. No people.",
 "kwon_05_school":   "An empty classroom of a 1910s Korean girls' school: plain wooden desks, a blackboard, tall paper-paned windows. No people.",
 "kwon_06_cockpit":  "The open cockpit of a 1920s biplane seen from above: round instrument dials and a control stick, worn leather rim. Close view. No people.",
 "kwon_07_sky":      "A view above a layer of clouds, an indistinct horizon line far away, pale light. No aircraft, no people.",
 "kwon_08_harbor":   "The Huangpu riverfront of Shanghai in the 1920s: a wooden jetty and moored steamships, seen from far away in mist. No people.",
 "kwon_09_logbook":  "A worn flight logbook lying open on a desk with a fountain pen beside it. Close view, handwriting illegible. No people.",
 "kwon_10_desk":     "A 1950s government office: a wooden desk with stacked document folders and a plain chair, shuttered window. No people.",
 "kwon_11_road":     "A dirt road receding into winter fog across empty fields, bare distant trees. No people.",
 "kwon_12_stone":    "A row of low gravestones in a national cemetery in winter, seen from far away, bare trees and pale light. Inscriptions illegible. No people.",
 # 13화 후세 다쓰지 — 1911~1927 법정
 "fuse_01_court":  "Interior of a 1920s Japanese courtroom: empty wooden public benches and tall windows. No people.",
 "fuse_02_robe":   "A worn judicial robe hanging on a wooden stand in a dim room. Close view. No people.",
 "fuse_03_tokyo":  "The stone facade of a 1920s Tokyo courthouse seen from a distance, overcast. No people.",
 "fuse_04_seoul":  "A 1920s Keijo (Seoul) street of tiled roofs and utility poles, seen from far away. No people.",
 "fuse_05_moat":   "A palace moat and stone bridge in early morning mist, seen from a distance. No people.",
 "fuse_06_desk":   "An empty defense counsel's wooden table with a bundle of tied documents. Close view, handwriting illegible. No people.",
 "fuse_07_paper":  "Old manuscript paper, a fountain pen and an ink bottle on a desk. Close view, handwriting illegible.",
 "fuse_08_dorm":   "An empty 1910s Tokyo student boarding room: bare tatami and a low writing desk. No people.",
 "fuse_09_medal":  "An old medal case and a folded ribbon. Close view. No people.",
 "fuse_10_shelf":  "A dusty bookshelf with worn book spines in dim light. Close view, titles illegible.",
 "fuse_11_strait": "Small waves of a strait and a far horizon under an overcast sky, seen from a distance. No people.",
 # 14화 최익현 — 1906 태인의병
 "choi_01_seowon": "The tiled eaves and empty courtyard of a Joseon confucian academy at early morning, 1900s. No people.",
 "choi_02_flag":   "An old plain cotton banner tied to a bamboo pole. Close view, no legible writing. No people.",
 "choi_03_field":  "Wide fields and low ridgelines of southwestern Korea, seen from a distance. No people.",
 "choi_04_road":   "A dirt road and paddy banks after rain, village roofs far away. No people.",
 "choi_05_ridge":  "Low misty hills and a bamboo grove over an empty field near Sunchang, seen from a distance. No people.",
 "choi_06_gate":   "The closed wooden gate and stone steps of a Joseon government office. No people.",
 "choi_07_hall":   "The interior of a Joseon government office: an empty chair and a low writing table, dim light. No people.",
 "choi_08_brush":  "An inkstone, a brush and an unrolled sheet of hanji paper. Close view, writing illegible.",
 "choi_09_sea":    "Winter waves of a strait and the shadow of a far island under an overcast sky. No people.",
 "choi_10_cell":   "A prison room with stone walls and a high barred window, light falling on the floor. No people.",
 "choi_11_dawn":   "The first winter daylight breaking over the sea and the horizon. No people.",

 # 15화 신채호 — 1906~1936
 "shin_01_wall":   "A high brick wall with barbed wire under an overcast winter sky, seen from a distance. No people.",
 "shin_02_inkstone": "An old inkstone and a worn writing brush. Close view. No people.",
 "shin_03_prison": "The red brick exterior and narrow windows of a 1930s Chinese prison in snow. No people.",
 "shin_04_corridor": "A prison corridor lined with iron doors and high barred windows, light on the floor. No people.",
 "shin_05_press":  "A 1900s newspaper letterpress machine and a typesetting table. Close view. No people.",
 "shin_06_manuscript": "A stack of manuscript sheets, a fountain pen and a dim lamp. Close view, writing illegible.",
 "shin_07_ledger": "The blank ruled columns of an old register and a seal stamp, dust. Close view, writing illegible.",
 "shin_08_declaration": "A single folded printed sheet lying on a wooden table. Close view, text illegible.",
 "shin_09_window": "A small barred window high on a cell wall with light seeping through. No people.",
 "shin_10_paper":  "An empty modern document envelope and a seal stamp on a desk. Close view, text illegible.",
 "shin_11_snow":   "A snow-covered yard and low wall, untouched white ground. No people.",
 "shin_12_registers": "A stack of old household register books tied with cord on a government office desk. Close view, writing illegible. No people.",
 # 17·18화 추가 컷
 "park_12_lockup": "A 1920s police station lockup: wooden bars and a dark corridor with light falling on the floor. No people.",
 "park_11_bowl":   "An untouched bowl of rice and a brass spoon on a prison cell floor. Close view. No people.",
 "maria_11_tokyo": "A 1910s Tokyo western-style brick building and bare winter street trees, seen from a distance. No people.",
 "maria_13_campus": "The stone buildings and lawn of a 1920s American university campus in autumn, seen from a distance. No people.",
 "maria_12_clinic": "A small 1910s Korean clinic consulting room: a wooden desk and glass medicine bottles, dim window. No people.",
 # 16화 이석영 — 1910 망명·신흥무관학교
 "seok_01_field":  "A wide plain and low hills in Seogando, Manchuria in early spring, seen from a distance. No people.",
 "seok_02_deed":   "Old Korean land deeds and a red seal on a low wooden table. Close view, writing illegible. No people.",
 "seok_03_river":  "The frozen Amnok river and the bare plain on the far bank in winter, seen from a distance. No people.",
 "seok_04_school": "A log schoolhouse and a low fence alone on the Manchurian plain, early spring. No people.",
 "seok_05_gate":   "The tall gate and stone wall of a Joseon aristocratic house, closed doors. No people.",
 "seok_06_yard":   "A bare earth parade ground and a bell hanging on a wooden post, morning light. No people.",
 "seok_07_road":   "A snow-covered border road with cart wheel ruts, seen from a distance. No people.",
 "seok_08_alley":  "A narrow back alley of 1930s Shanghai: brick walls and washing lines. No people.",
 "seok_09_bowl":   "A chipped earthenware bowl and a wooden spoon on a worn low table. Close view. No people.",
 "seok_11_grave":  "Low gravestones and dry grass in an old public cemetery under pale light, seen from a distance. Inscriptions illegible. No people.",
 "seok_10_hall":   "The interior of a simple log meeting house in Manchuria: a bare earthen floor, a long plank table and low benches. No people.",

 # 17화 박재혁 — 1920 부산경찰서 투탄
 "park_01_station": "The stone facade and closed door of a 1920s Japanese-style police station, seen from a distance. No people.",
 "park_02_books":   "A pile of old Korean-bound books tied with cord. Close view, titles illegible. No people.",
 "park_03_shelf":   "Shelves packed with old Chinese books and dust. Close view, titles illegible. No people.",
 "park_04_bundle":  "A bundle of books wrapped in cloth with a tie, on a wooden floor. Close view. No people.",
 "park_05_table":   "A 1920s office: a wooden table with two chairs facing each other, a dim window. No people.",
 "park_06_harbor":  "The wooden jetty and moored boats of 1920s Busan harbour with far hills, seen from a distance. No people.",
 "park_07_smoke":   "A room with a shattered window, scattered paper and drifting smoke. No people.",
 "park_08_pier":    "The hull of a steamship and mooring ropes at a 1920s Shanghai pier in mist. No people.",
 "park_09_cell":    "A prison cell with a stone floor and a high barred window, light falling in. No people.",
 "park_10_sea":     "An early spring sea and a far horizon under an overcast sky. No people.",

 # 18화 김마리아 — 1919 2·8독립선언서
 "maria_02_obi":    "A folded kimono sash with a folded sheet of paper lying on it. Close view, text illegible. No people.",
 "maria_03_paper":  "Several old mimeographed sheets overlapping on a table. Close view, text illegible. No people.",
 "maria_04_port":   "The wooden jetty and cargo of 1910s Busan harbour with a distant steamship. No people.",
 "maria_05_school": "An empty 1910s Korean girls' school classroom with wooden desks and dim window light. No people.",
 "maria_06_ship":   "The gunwale and mooring ropes of a ferry tied at a quay. Close view. No people.",
 "maria_07_room":   "An empty meeting room with a round table and chairs, dim window. No people.",
 "maria_08_court":  "The empty defendant's rail and wooden wall of a 1920s courtroom. No people.",
 "maria_09_ward":   "A 1940s hospital corridor with an iron bed frame and tall windows. No people.",
 "maria_10_quay":   "The stone steps of an empty winter quay and small ripples. No people.",

 # 19화 헐버트 — 1905 워싱턴·1907 헤이그
 "hul_01_capitol":   "A 1900s Washington stone government building and its steps, seen from a distance. No people.",
 "hul_02_letter":    "An old envelope sealed with wax. Close view, writing illegible. No people.",
 "hul_03_door":      "A closed wooden government office door with a brass handle and a long corridor. Close view. No people.",
 "hul_04_hague":     "A 1900s Dutch city canal and gabled houses, seen from a distance. No people.",
 "hul_05_book":      "An open old textbook printed in Korean hangul type. Close view, text illegible. No people.",
 "hul_06_classroom": "An empty 1880s western-style schoolroom in Korea: wooden desks and a blackboard. No people.",
 "hul_07_pier":      "The wooden steps of a 1940s Incheon pier and a moored ship under a cloudy sky. No people.",
 "hul_08_grave":     "A single low gravestone on grass with autumn leaves, seen from a distance. Inscription illegible. No people.",
 "hul_09_medal":     "An old medal case and a folded ribbon. Close view. No people.",
 "hul_10_road":      "A misty river and low hills at early morning, seen from a distance. No people.",

 # 20화 안규홍 — 1908 보성의병
 "ahn20_01_village": "A rural Jeolla village of thatched roofs and stone walls in the 1900s, seen from a distance. No people.",
 "ahn20_02_tool":    "A worn A-frame carrier and a sickle leaning against an earthen wall. Close view. No people.",
 "ahn20_03_hill":    "Low southern Korean hills and paddies in early spring mist, seen from a distance. No people.",
 "ahn20_04_lamp":    "An oil lamp and a few bowls in an earthen-floored room at night. Close view. No people.",
 "ahn20_05_ridge":   "Dry silver grass on a ridge with drifting smoke under a cloudy sky, seen from a distance. No people.",
 "ahn20_06_path":    "A narrow mountain path through a bamboo grove with footprints, seen from a distance. No people.",
 "ahn20_07_field":   "An empty harvested paddy with rice straw bundles in late autumn light, seen from a distance. No people.",
 "ahn20_08_yard":    "An earthen yard with stacked firewood and a worn straw mat. Close view. No people.",
 "ahn20_09_court":   "The empty wooden rail and tall windows of a 1910s courtroom. No people.",
 "ahn20_10_wall":    "The brick wall and iron gate outside a prison at early morning. No people.",
 "ahn20_11_sky":     "An early summer sky and a far mountain ridge, seen from a distance. No people.",
 # v3-1 추푸청 — 1932 윤봉길 의거 뒤 김구 피신 (컬러, STYLE_COLOR)
 "chu_01_park":    "Hongkou Park in Shanghai in spring 1932 seen from a distance: an empty speakers' platform draped with cloth, trampled grass, drifting smoke. No people.",
 "chu_02_notice":  "A wanted poster pasted on a weathered 1930s Shanghai brick wall, torn edges, rain streaks. Text unreadable and blurred. No people.",
 "chu_03_street":  "A 1930s Shanghai French Concession street at dusk: plane trees, shuttered shop fronts, wet cobblestones, a single tram in the distance. No people.",
 "chu_04_study":   "A 1930s Chinese scholar's study: a rosewood desk with an inkstone, stacked thread-bound books and a lamp, lattice window. No people.",
 "chu_05_train":   "A 1930s steam train crossing flat green Jiangnan farmland seen from far away, white smoke trailing. No people.",
 "chu_06_canal":   "A quiet canal town in Jiaxing, China in the 1930s: whitewashed houses with black tiled roofs reflected in still water, stone bridge. No people.",
 "chu_07_mill":    "The interior of a small 1930s paper mill: stacks of paper, wooden drying racks, light through high windows. No people.",
 "chu_08_boat":    "A small wooden rowboat with a woven bamboo canopy drifting on a misty South Lake in Jiaxing, reeds at the edge. Figures only as a tiny silhouette from behind at the stern.",
 "chu_09_path":    "A narrow mountain path through bamboo and tea bushes near the sea in Haiyan, China, soft morning light. No people.",
 "chu_10_villa":   "A modest 1930s Chinese villa with a tiled roof on a hillside by the sea, seen from a distance, overcast. No people.",
 "chu_11_lake":    "South Lake in Jiaxing at dawn: a calm lake, a pavilion on a small island far away, pale mist. No people.",
 "chu_12_letter":  "An old handwritten letter in Chinese brush script and a folded envelope on a wooden table beside a teacup. Close view, writing illegible. No people.",
 # v3-02 김용환 — 안동 학봉 종손, 군자금 (흑백 렌더)
 "kyh_01_tujeon":   "A low wooden table in a dim 1920s Korean room: scattered old playing sticks (tujeon), a brass bowl of coins, a spilled rice-wine cup, an oil lamp. Close view. No people.",
 "kyh_02_jongtaek": "A large traditional Korean head-family house (jongtaek) in Andong: tiled roofs, wooden pillars, stone steps, an old zelkova tree, morning haze, seen from a distance. No people.",
 "kyh_03_manchuria":"A vast winter plain in Manchuria under a grey sky, a distant line of low log buildings and bare trees, thin snow. No people.",
 "kyh_04_bridge":   "The long iron railway bridge over the Amnok river at Sinuiju around 1920 seen from the riverbank, a steam train small in the distance, mist. No people.",
 "kyh_05_cell":     "A 1920s prison corridor: a heavy iron door with a small barred window, plaster wall, faint light on a stone floor. No people.",
 "kyh_06_road":     "A dirt road between rice paddies leading toward distant mountains in Andong, overcast, a single roadside marker stone. No people.",
 "kyh_07_house":    "The gate of a Korean aristocratic house left open, yard swept, a wooden signboard above the gate with characters unreadable, late afternoon light. No people.",
 "kyh_08_field":    "Wide paddy fields in front of a tiled-roof Korean house, early summer, water reflecting the sky, seen from a slight height. No people.",
 "kyh_09_letter":   "A sheet of Korean hanji paper with vertical brush handwriting and a folded envelope on a low wooden table, a worn brush beside it. Close view, writing illegible. No people.",
 "kyh_10_medal":    "An old medal on a folded ribbon resting on a plain wooden shelf next to a small framed empty photo mount, soft window light. Close view. No people.",
 # v3-03 윤봉길 — 1932 훙커우 의거, 김구와 바꾼 시계 (컬러)
 "yun_01_watch":   "Two old pocket watches lying side by side on a plain wooden table in a 1930s Shanghai room, morning light from a window, one watch slightly worn. Close view. No people.",
 "yun_02_park":    "Hongkou Park in Shanghai on a spring morning in 1932: a large wooden ceremonial platform draped in cloth, rows of empty chairs, trees in fresh leaf. No people.",
 "yun_03_village": "A rural village in Chungcheong, Korea in the 1920s: thatched-roof houses, a small night-school building with a paper lantern, fields at dusk. No people.",
 "yun_04_classroom":"A small 1920s Korean village night school interior: low wooden desks, a blackboard, an oil lamp, a few worn books. No people.",
 "yun_05_road":    "A dirt road leaving a Korean village at dawn, frost on the ground, a lone bundle on a stick resting against a roadside tree. No people.",
 "yun_06_shanghai":"A 1930s Shanghai street seen from a distance: rickshaws, signboards with unreadable characters, plane trees, morning haze. Figures only as distant silhouettes.",
 "yun_07_breakfast":"A simple breakfast on a low table in a 1930s Shanghai lodging: two bowls of rice, kimchi, a teapot, sunlight on the table. Close view. No people.",
 "yun_08_letter":  "A handwritten letter in Korean brush script on thin paper, folded once, lying beside a fountain pen on a dark desk. Close view, writing illegible. No people.",
 "yun_09_snow":    "A bare hillside near Kanazawa, Japan in December: thin snow, a few dark pines, grey sky, a narrow path. No people.",
 "yun_10_hyochang":"Hyochang Park in Seoul: a grassy burial mound with a stone marker, pine trees, soft afternoon light. Inscription illegible. No people.",
 # v3-04 사명대사 — 1604~05 일본행, 포로 3천여 명 송환 (컬러)
 "sam_01_sea":     "A single wooden Joseon sailing ship crossing a grey strait toward distant islands at dawn, 17th century, mist on the water. No people.",
 "sam_02_temple":  "A quiet Joseon-era mountain temple courtyard in autumn: stone lantern, wooden hall, fallen leaves, a monk's straw sandals on the step. No people.",
 "sam_03_ruins":   "A burned Korean village after the Imjin war, 1590s: charred timber, broken tiled roofs, an empty road, smoke in the distance. No people.",
 "sam_04_chains":  "A pile of rusted iron shackles and rope on a stone floor of a 17th-century Japanese port warehouse, dim light. Close view. No people.",
 "sam_05_kyoto":   "Kyoto in the early 17th century seen from a distance: tiled roofs, a castle keep, pine trees, morning haze. No people.",
 "sam_06_hall":    "A Japanese castle audience hall of the early 1600s: tatami floor, gold-leaf sliding screens, a low writing table, soft light. No people.",
 "sam_07_road":    "A long line of people walking along a coastal road toward a harbor at sunset, seen from far away as tiny silhouettes, 17th century Japan.",
 "sam_08_harbor":  "Busan harbor in the early 17th century: wooden ships moored, low hills, a stone quay, spring light. No people.",
 "sam_09_brush":   "A calligraphy brush, inkstone and a sheet of paper with a few vertical strokes on a low wooden table in a temple room. Close view, characters unreadable. No people.",
 "sam_10_shrine":  "The wooden shrine hall of Pyochungsa in Miryang, Korea: red pillars, a signboard with characters unreadable, pine trees, soft afternoon light. No people.",
 # v3-05 나석주 — 1926 동척·식산은행 투탄 (컬러, 주인공은 뒷모습·실루엣만)
 "nsj_01_street":  "A winter street in 1920s Seoul (Hwanggeum-jeong): tram tracks, electric poles, grey stone buildings. A man in a dark Chinese long gown and felt hat is seen only from behind, walking toward a large stone company building. Cinematic.",
 "nsj_02_building":"The imposing stone facade of a 1920s Japanese colonial company headquarters in Seoul: tall columns, heavy doors, a Japanese flag, winter light, seen from the street. Figures only as tiny distant silhouettes.",
 "nsj_03_fields":  "Korean tenant farmers seen from behind carrying heavy rice sacks along a dirt road toward a Japanese company warehouse in 1920s Hwanghae province, harvested fields, grey sky.",
 "nsj_04_home":    "A poor thatched-roof farmhouse in Hwanghae, Korea in winter; a young man seen from behind standing at the edge of a field that is no longer his, looking at it.",
 "nsj_05_letter":  "A handwritten Korean brush letter on a desk in a cold 1920s Chinese rented room, a revolver and a small cloth bundle beside it, a candle. Close view, writing illegible. No people.",
 "nsj_06_bank":    "Interior of a 1920s colonial bank hall in Seoul: marble counter, clerks' desks, a round iron bomb lying unexploded on the floor in the foreground. People only as blurred silhouettes in the background.",
 "nsj_07_stairs":  "A man in a dark overcoat seen from behind climbing the stone staircase inside a 1920s office building, a revolver in his hand, dramatic side light, dust in the air.",
 "nsj_08_office":  "A 1920s Japanese company office in chaos: overturned chairs, scattered papers, drifting smoke, an unexploded round bomb on the wooden floor. No people.",
 "nsj_09_chase":   "A snowy 1920s Seoul street at dusk: a lone man seen from behind running across tram tracks, blurred silhouettes of policemen chasing in the distance, motion blur.",
 "nsj_10_pole":    "A dropped revolver and a felt hat lying in the snow beside a wooden telegraph pole on an empty 1920s Seoul street at dusk. No people.",
 # v3-06 이윤재 — 조선어학회 사건 (그림체, 주인공 등장·정면 얼굴 없음)
 "lyj_01_cell":    "Inside a cold concrete solitary prison cell in winter; the scholar sits on the floor with his back to the viewer, loose handwritten manuscript pages scattered around him, a single shaft of pale light from a tiny barred window.",
 "lyj_02_desk":    "A 1930s Seoul study at night lit by one oil lamp; the scholar seen from behind and slightly to the side, bent over a desk writing a Korean dictionary manuscript, stacks of paper and books around him.",
 "lyj_03_cards":   "A long wooden table covered with thousands of small handwritten word index cards in wooden trays; only the scholar's hands and hanbok sleeves are visible, sorting the cards. Warm lamplight.",
 "lyj_04_gate":    "Outside a colonial-era prison gate of red brick on a snowy morning; the scholar walks away from the gate, seen from behind, carrying a cloth-wrapped bundle of books under his arm.",
 "lyj_05_diary":   "A schoolgirl's open diary on a wooden desk in a 1940s girls' school dormitory; a Japanese policeman's white-gloved hand points at one line. Text illegible. No faces.",
 "lyj_06_arrest":  "A snowy night street in 1940s Korea; Japanese police in dark uniforms lead several Korean scholars in hanbok away, all seen from behind, the main scholar among them with his round glasses glinting in lamplight.",
 "lyj_07_seized":  "Japanese policemen carrying wooden crates stuffed with manuscript bundles out of an office; the scholar stands in the foreground seen from behind, held by the arm, watching them.",
 "lyj_08_room":    "A bare 1940s interrogation room: a wooden chair, a metal bucket of water, a single hanging bulb; the scholar's shadow cast large on the wall, his figure turned away. Somber, no gore.",
 "lyj_09_dawn":    "A solitary prison cell at a freezing winter dawn; the scholar's silhouette slumped against the wall, turned away from the viewer, breath mist in the air, his round glasses lying on the floor.",
 "lyj_10_station": "A dim 1945 Seoul railway station warehouse; a station worker seen from behind opens a wooden crate full of yellowed Korean manuscript bundles, dust glittering in the light from a half-open door.",
 # v3-07b 문형순 컬러판 — 주인공 뒷모습 (mflux)
 "mhsc_01_desk":    "At night in a 1950 police chief's office, the police chief sits at a wooden desk seen from directly behind, reading a single typed official document under a green desk lamp. Over-the-shoulder view, the document text illegible.",
 "mhsc_02_jeju":    "Summer 1950 on Jeju island: the police chief stands on a path between black basalt stone walls, seen from behind, looking toward the Seongsan Ilchulbong crater across a village of low thatched roofs, overcast sky.",
 "mhsc_03_station": "The police chief walks toward the entrance of a small 1950 rural police station with a tiled roof and a basalt stone wall, seen from behind in the dirt yard, late afternoon light.",
 "mhsc_04_room":    "The police chief stands in the open barred wooden door of a dim 1950 warehouse holding room, seen from behind; inside, many detained villagers in plain clothes sit on straw mats, blurred and out of focus.",
 "mhsc_05_pen":     "Extreme close-up of the police chief's hand in a dark navy uniform sleeve holding a fountain pen, writing a short handwritten line at the top of a typed official document. Writing illegible. Only the hand visible.",
 "mhsc_06_rice":    "A mid-1950s Korean rice ration depot. A single slim middle-aged man with short greying hair, bareheaded (no hat, no cap), wearing a plain worn grey civilian work jacket, seen completely from behind as he lifts a straw rice sack onto a stack. He is alone: no police, no uniforms, no other people. Dusty light from the doorway.",
 "mhsc_07_ward":    "A 1966 provincial Korean hospital ward, quiet afternoon. A single old man with thin grey hair lies alone in an iron bed by the window, his body turned away from the viewer toward the window so only the back of his head and shoulders are visible. The rest of the room is empty: no nurses, no visitors, no police, no other people. An empty wooden chair beside the bed.",
 "mhsc_08_cap":     "A 1950s Korean police officer's peaked cap and a pair of round wire-rimmed glasses resting on a folded official document on a wooden table, soft window light. Close view. No people.",
 "mhsc_09_road":    "Dawn on a dirt country road through Jeju fields: in the foreground the police chief stands seen from behind, watching a small group of villagers walk away toward their village in the mist.",
 "mhsc_10_village": "Moseulpo harbor, Jeju, around 1949: the police chief stands on the stone pier seen from behind, looking at a coastal village of low stone-walled houses and small wooden fishing boats, villagers tiny in the distance.",
 "mhsc_11_cemetery":"Rows of simple white granite gravestones in a Korean national cemetery on a green hillside, white chrysanthemums, soft morning mist. No people.",
 # v3-07 문형순 — 1950 성산포 예비검속 총살 명령 거부 (mflux 로컬 생성)
 "mhs_01_order":   "Close view of a single 1950 Korean official government document on a worn wooden desk, typed vertical Korean lines and a round red ink seal, a fountain pen beside it, desk lamp light. Text illegible. No people.",
 "mhs_02_jeju":    "A 1950 Jeju island coastal village in summer: black basalt stone walls, low thatched-roof houses, the Seongsan Ilchulbong crater rising in the distance, overcast sky. No people.",
 "mhs_03_station": "A small 1950 rural Korean police station building: low wooden structure with a tiled roof, a bare flagpole, a dirt yard enclosed by a basalt stone wall. No people.",
 "mhs_04_room":    "An empty 1950 warehouse holding room with straw mats on an earthen floor, a barred wooden door, thin light through gaps in the plank wall. No people.",
 "mhs_05_pen":     "Extreme close-up of a man's hand in a dark uniform sleeve holding a fountain pen, writing a short handwritten line at the top of a typed official document. Writing illegible. Only the hand visible.",
 "mhs_06_rice":    "A 1950s Korean rice ration depot: stacked straw rice sacks, a wooden measuring box and scale, dusty light from a doorway. No people.",
 "mhs_07_ward":    "An empty 1960s provincial hospital ward: a single iron bed with white sheets by a window, a folded blanket, bare walls, quiet afternoon light. No people.",
 "mhs_08_cap":     "A 1950s Korean police officer's peaked cap resting on a folded official document on a wooden table, dim window light. Close view. No people.",
 "mhs_09_road":    "A dirt country road through Jeju fields at dawn, a small group of villagers walking away toward a village, seen only from far behind as tiny silhouettes, mist over the fields.",
 "mhs_10_village": "Moseulpo, Jeju, around 1949: a coastal village of low stone-walled houses by a harbor with small wooden fishing boats, wide view. No people.",
 "mhs_11_cemetery":"Rows of simple white granite gravestones in a Korean national cemetery on a hillside, a few white chrysanthemums, morning mist. No people.",
}


# v3-07b 문형순 컬러판 (2026-09-26 사용자 지시 — "인물 뒷모습 나오는 이미지, 컬러로"). 그림체가 아니라 실사 컬러.
STYLE_COLOR_CHAR = ("The main character appears in the scene but NEVER with a visible face — show him from behind, "
                    "turned away, in shadow, or only his hands. Other people only as distant or blurred figures.")
PHOTO_CHAR = {
    "mhsc_": ("a Korean police chief in his early fifties (1950), slim build, short dark hair greying at the temples, "
              "round wire-rimmed glasses, wearing a dark navy Korean National Police uniform and peaked cap. Always the same man."),
}


def _style_for(key, scene):
    for pre, who in PHOTO_CHAR.items():
        # 인물 없는 컷, 경찰을 그만둔 뒤의 컷(제복 설명을 붙이면 경찰이 끼어든다 — 2026-09-26)은 컬러 스타일만
        if key.startswith(pre) and ("No people" in scene or "no police" in scene):
            return f"Image: {scene} {STYLE_COLOR}"
        if key.startswith(pre):
            return f"Image: {scene} Main character: {who} {STYLE_COLOR_CHAR} {STYLE_COLOR}"
    for pre, who in ILLUST.items():
        if key.startswith(pre):
            return f"Image: {scene} Main character: {who} {STYLE_ILLUST}"
    return f"Image: {scene} {STYLE_COLOR if key.startswith(COLOR_PREFIXES) else STYLE}"


SSUL = os.path.expanduser("~/Desktop/kim/ssul")
SDXL_PY = os.path.join(SSUL, "sdvenv/bin/python3")
SDXL_GEN = os.path.join(SSUL, "pipeline/gen_local.py")


# GPT 이미지는 전역 codex-image gen.sh 로만 뽑는다 — 가장 싼 모델 + GPT는 생성만(2026-09-26).
# codex exec 를 직접 부르면 기본 최상위 모델이 저장·검증까지 돌아 장당 한도를 5배 넘게 먹는다.
GEN_SH = os.path.expanduser("~/.claude/skills/codex-image/scripts/gen.sh")


def generate_codex(key, scene):
    path = os.path.join(OUT, key + ".png")
    r = subprocess.run(["bash", GEN_SH, "--prompt", _style_for(key, scene), "--out", path,
                        "--orientation", "landscape", "--width", "1024", "--height", "768"],
                       cwd=BASE, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    ok = os.path.exists(path) and os.path.getsize(path) > 50_000
    return ok, (r.stdout or "")[-400:] + (r.stderr or "")[-400:]


def generate_sdxl(key, scene):
    """codex 가 막혔을 때만 — ssul 의 로컬 SDXL 로 뽑고 4:3(1024×768)으로 크롭한다."""
    path = os.path.join(OUT, key + ".png")
    env = dict(os.environ, SDXL_GEN_W="768", SDXL_GEN_H="480",
               PYTORCH_MPS_HIGH_WATERMARK_RATIO="0.0", PYTORCH_ENABLE_MPS_FALLBACK="1")
    r = subprocess.run([SDXL_PY, SDXL_GEN, "--prompt", _style_for(key, scene), "--out", path, "--fast"],
                       cwd=SSUL, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL)
    if os.path.exists(path):
        from PIL import Image
        im = Image.open(path); w, h = im.size; nw = int(h * 4 / 3)
        im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h)).resize((1024, 768), Image.LANCZOS).save(path)
    ok = os.path.exists(path) and os.path.getsize(path) > 50_000
    return ok, (r.stdout or "")[-400:] + (r.stderr or "")[-400:]


def generate(key, scene):
    ok, tail = generate_codex(key, scene)
    if ok:
        return ok, tail
    if not os.path.exists(SDXL_PY):  # 2026-09-26 로컬 SDXL 삭제 — 재설치 전까진 codex 만
        return ok, tail
    print(f"  {key:18s} codex 실패 → 로컬 SDXL 로 대체")
    return generate_sdxl(key, scene)


def main(prefixes):
    keys = [k for k in SCENES if not prefixes or any(k.startswith(p) for p in prefixes)]
    made = skipped = 0
    for k in keys:
        path = os.path.join(OUT, k + ".png")
        if os.path.exists(path) and os.path.getsize(path) > 50_000:
            print(f"  {k:18s} 있음 — 건너뜀"); skipped += 1; continue
        ok, tail = generate(k, SCENES[k])
        if not ok:
            print(f"  {k:18s} ❌ 실패 — 여기서 멈춘다\n{tail}")
            print(f"\n생성 {made}장 / 건너뜀 {skipped}장 / 남은 {len(keys)-made-skipped}장")
            return 1
        print(f"  {k:18s} ✅ {os.path.getsize(path):,} bytes"); made += 1
    print(f"\n생성 {made}장 / 건너뜀 {skipped}장 — 전부 채움")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
