import streamlit as st
import json
import glob
import os
from supabase import create_client

# ページ設定
st.set_page_config(page_title="社労士 選択式マスター", layout="wide")

# =========================
# 1. Supabase接続
# =========================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    st.error("SupabaseのSecrets設定が不足しています。")
    st.stop()

# =========================
# 2. 問題読み込み
# =========================
@st.cache_data
def load_questions():
    all_data = {}
    # ファイル名が "01_労基.json" のような形式を想定
    json_files = sorted(glob.glob("*.json"))
    for file_path in json_files:
        name = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # 選択式(selection)のデータのみ抽出
            all_data[name] = [q for q in data if q.get("type") == "selection"]
    return all_data

questions_dict = load_questions()

# =========================
# 3. セッション状態の初期化
# =========================
if "s_index" not in st.session_state: st.session_state.s_index = 0
if "s_answered" not in st.session_state: st.session_state.s_answered = False
if "s_wrong_ids" not in st.session_state: st.session_state.s_wrong_ids = set()
if "current_cat" not in st.session_state: st.session_state.current_cat = ""
if "db_synced" not in st.session_state: st.session_state.db_synced = False

# =========================
# 4. DB同期
# =========================
def sync_db(user_id):
    if user_id and not st.session_state.db_synced:
        try:
            res = supabase.table("wrong_questions_selection").select("question_id").eq("user_id", user_id).execute()
            st.session_state.s_wrong_ids = {item["question_id"] for item in res.data}
            st.session_state.db_synced = True
        except:
            st.warning("DB同期に失敗しました。")

# =========================
# 5. サイドバー
# =========================
with st.sidebar:
    st.title("🎯 選択式トレーニング")
    u_id = st.text_input("ユーザーID", placeholder="ID入力で保存有効")
    if u_id: sync_db(u_id)
    
    cat_list = list(questions_dict.keys())
    selected_cat = st.selectbox("科目選択", cat_list)
    
    if selected_cat != st.session_state.current_cat:
        st.session_state.current_cat = selected_cat
        st.session_state.s_index = 0
        st.session_state.s_answered = False
        st.rerun()
        
    mode = st.radio("学習モード", ["通常学習", "苦手克服 🔥"])

# 問題抽出
target = questions_dict.get(selected_cat, [])
if mode == "苦手克服 🔥":
    target = [q for q in target if q["id"] in st.session_state.s_wrong_ids]

if not target:
    st.info("対象の問題がありません。")
    st.stop()

# インデックス調整
idx = st.session_state.s_index % len(target)
q = target[idx]

# =========================
# 6. メイン画面
# =========================
st.title(f"【{selected_cat}】")
st.progress((idx + 1) / len(target))

with st.container(border=True):
    st.markdown(f"#### 問題 ID: {q['id']}")
    # 穴埋め箇所を強調表示
    display_q = q["q"].replace("（", " **（ ").replace("）", " ）** ")
    st.markdown(display_q)

st.divider()

# 回答入力エリア
st.write("各空欄を選択してください：")
user_choices = {}
cols = st.columns(len(q["options"]))
for i, (label, opts) in enumerate(q["options"].items()):
    with cols[i]:
        user_choices[label] = st.selectbox(f"空欄 {label}", ["-"] + opts, key=f"q_{q['id']}_{label}")

# 判定ボタン
if st.button("採点する", use_container_width=True) or st.session_state.s_answered:
    st.session_state.s_answered = True
    
    # 全空欄チェック
    results = {label: (user_choices[label] == q["a"][label]) for label in q["a"]}
    all_correct = all(results.values())
    
    if all_correct:
        st.success("🎉 全問正解！")
        if q["id"] in st.session_state.s_wrong_ids:
            st.session_state.s_wrong_ids.remove(q["id"])
            if u_id:
                supabase.table("wrong_questions_selection").delete().eq("user_id", u_id).eq("question_id", q["id"]).execute()
    else:
        st.error("❌ 不正解があります")
        wrong_parts = [k for k, v in results.items() if not v]
        st.session_state.s_wrong_ids.add(q["id"])
        
        # DB保存
        if u_id:
            supabase.table("wrong_questions_selection").upsert({
                "user_id": u_id,
                "question_id": q["id"],
                "category_id": selected_cat[:2], # 先頭2文字(01など)を想定
                "category_name": selected_cat,
                "wrong_parts": ",".join(wrong_parts)
            }).execute()
        
        # 正解表示
        cols_ans = st.columns(len(q["a"]))
        for i, (l, a) in enumerate(q["a"].items()):
            cols_ans[i].markdown(f"**{l}の正解:**\n{a}")

    st.info(f"💡 **解説**\n\n{q['tips']}")

    if st.button("次の問題へ ➡️", use_container_width=True):
        st.session_state.s_index += 1
        st.session_state.s_answered = False
        st.rerun()

# ステータス表示
st.sidebar.divider()
st.sidebar.write(f"現在の科目の苦手: `{len([i for i in st.session_state.s_wrong_ids if any(x['id']==i for x in target)])}` 問")