import streamlit as st
import json
import glob
import os
from supabase import create_client

st.set_page_config(page_title="社労士 選択式マスター", layout="wide")

# =========================
# Supabase接続 (選択式専用テーブル: wrong_questions_selection)
# =========================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# =========================
# 問題読み込み
# =========================
@st.cache_data
def load_selection_questions():
    all_data = {}
    # 選択式専用のJSONファイルを読み込む（例: s_01_shaichi.json）
    json_files = glob.glob("s_*.json") 
    for file_path in json_files:
        subject_name = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8") as f:
            all_data[subject_name] = json.load(f)
    return all_data

questions_dict = load_selection_questions()

# =========================
# セッション状態
# =========================
if "s_index" not in st.session_state: st.session_state.s_index = 0
if "s_answered" not in st.session_state: st.session_state.s_answered = False
if "s_wrong_ids" not in st.session_state: st.session_state.s_wrong_ids = set()

# =========================
# サイドバー
# =========================
with st.sidebar:
    st.title("🎯 選択式トレーニング")
    user_id = st.text_input("ユーザーID", key="s_user")
    category = st.selectbox("科目", list(questions_dict.keys()))
    mode = st.radio("モード", ["全問学習", "苦手克服"])

target = questions_dict.get(category, [])
if mode == "苦手克服":
    target = [q for q in target if q["id"] in st.session_state.s_wrong_ids]

if not target:
    st.info("問題がありません。")
    st.stop()

q = target[st.session_state.s_index % len(target)]

# =========================
# メイン表示
# =========================
st.subheader(f"【{category}】 ID: {q['id']}")
st.markdown("### 問題文")
st.info(q["q"]) # 問題文（A, B...が含まれる）

st.markdown("---")
st.markdown("### 解答選択")

# 空欄ごとにセレクトボックスを生成
user_choices = {}
cols = st.columns(len(q["options"]))
for i, (label, opts) in enumerate(q["options"].items()):
    with cols[i]:
        user_choices[label] = st.selectbox(f"空欄 【{label}】", ["-"] + opts)

if st.button("採点する", use_container_width=True) or st.session_state.s_answered:
    st.session_state.s_answered = True
    
    # 判定
    results = {}
    all_correct = True
    for label, correct_val in q["a"].items():
        is_correct = user_choices[label] == correct_val
        results[label] = is_correct
        if not is_correct: all_correct = False

    # 結果表示
    if all_correct:
        st.success("🎉 全問正解！")
        if q["id"] in st.session_state.s_wrong_ids:
            st.session_state.s_wrong_ids.remove(q["id"])
    else:
        st.error("❌ 不正解が含まれます")
        st.session_state.s_wrong_ids.add(q["id"])
        # 各空欄の正解を表示
        ans_text = " / ".join([f"{k}: {v}" for k, v in q["a"].items()])
        st.write(f"**正解一覧:** {ans_text}")

    st.markdown(f"💡 **解説:** {q['tips']}")

    if st.button("次の問題へ"):
        st.session_state.s_index += 1
        st.session_state.s_answered = False
        st.rerun()