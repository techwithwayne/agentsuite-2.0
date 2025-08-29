# 📝 Human Capital App — Full Test Checklist

## 🔧 Admin Side
- [x] Duplicate registration removed (`AlreadyRegistered` fixed).
- [x] AssessmentSession loads without crashing.
- [x] Inlines working: Skills, Cognitive, Personality, Behavior, Motivation.
- [x] ai_summary field visible and read-only.
- [ ] Add a new AssessmentSession in admin (verify save).
- [ ] Add inline records (Skills, Personality, etc.) directly inside a session (verify save).
- [ ] Check list views for all models.

---

## 🔧 User-Facing Flow
Visit each step in order:
- [ ] `/humancapital/` → Welcome page loads.
- [ ] `/humancapital/personal-info/` → Form renders (no 500).
- [ ] `/humancapital/skills/` → Form renders.
- [ ] `/humancapital/cognitive/` → Form renders.
- [ ] `/humancapital/personality/` → Form renders.
- [ ] `/humancapital/behavior/` → Form renders.
- [ ] `/humancapital/motivation/` → Form renders.
- [ ] `/humancapital/summary/` → Charts + AI summary (or safe fallback).

---

## 🤖 AI Summary Testing
- [ ] Complete an assessment session fully (all steps).
- [ ] On Summary page:
  - [ ] If OpenAI call works → summary text should appear.
  - [ ] If API fails → fallback `"AI summary could not be generated..."`.
- [ ] In Admin → open same AssessmentSession, confirm:
  - [ ] `ai_summary` field is populated with AI text.
  - [ ] If fallback triggered → `ai_summary` remains blank.

---

## 📊 Visualization Testing
- [ ] Summary page shows Skills bar chart.
- [ ] Summary page shows Personality radar chart.
- [ ] (Future) Behavior & Motivation charts render.
- [ ] Admin → AssessmentSession detail shows inline charts (Skills + Personality).

---

## 🔧 Logs
When errors happen:
```bash
grep humancapital /var/log/apps.techwithwayne.com.error.log | tail -n 30
