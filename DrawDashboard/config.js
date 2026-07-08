/**
 * config.js
 * Central configuration for the Random Draw Dashboard.
 * All data, colors, and tunable constants live here.
 */

const CONFIG = {

  /* ── App meta ─────────────────────────────────────────── */
  appTitle: "لوحة السحب العشوائي",
  appSubtitle: "نظام السحب الاحترافي",

  /* ── Default lists (overridden by LocalStorage) ────────── */
  defaultPeople: [
    "أثير الخليفة",
    "آمال المزروع",
    "الحسن العيساوي",
    "بدرية المطيري",
    "ريهام عبدالخالق",
    "سارة القحطاني",
    "سطام المرشود",
    "سلطان الفريح",
    "طلال آل جلفان",
    "عبدالرحمن العصيمي",
    "عبدالملك العبدالوهاب",
    "فهد النشوان",
    "مجد القرشي",
    "طلال الدلبحي"
  ],

  defaultGames: [
    "تصفية البريد اللغوي",
    "حيوان جماد نبات",
    "سلم المراتب",
    "حكيم الفروق",
    "فرز الكلمات - كبار",
    "فرز الكلمات - أطفال",
    "الصورة والكلمة",
    "جذور الكلمات",
    "فك الشفرة",
    "مع المتنبي",
    "كاس الاعراب",
    "خبير اللهجات"
  ],

  /* ── Wheel color palette (alternating sectors) ─────────── */
  wheelColors: [
    "#006C35", "#0F8A4B", "#1AA35C", "#2DB870",
    "#3DC97F", "#52D98F", "#006C35", "#0F8A4B",
    "#1AA35C", "#2DB870", "#3DC97F", "#52D98F",
    "#006C35", "#0F8A4B"
  ],

  /* ── Spin animation ─────────────────────────────────────── */
  spinMinDuration: 5000,   // ms
  spinMaxDuration: 7000,   // ms
  spinMinRotations: 8,     // full rotations minimum
  spinMaxRotations: 14,    // full rotations maximum

  /* ── LocalStorage keys ──────────────────────────────────── */
  storageKeys: {
    people:    "raqim_people",
    games:     "raqim_games",
    history:   "raqim_history",
    darkMode:  "raqim_dark",
    sound:     "raqim_sound",
    remaining: "raqim_remaining"
  }
};
