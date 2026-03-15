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
    st.error("SupabaseのSecrets設定を確認してください。")
    st.stop()

# =========================
# 2. 問題読み込み
# =========================
@st.cache_data
def load_questions():
    all_data = {}
    json_files = sorted(glob.glob("*.json"))
    for file_path in json_files:
        name = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
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
# 4. DB同期 (起動時・ユーザー変更時)
# =========================
def sync_db(user_id):
    u_id_clean = user_id.strip()
    if u_id_clean and not st.session_state.db_synced:
        try:
            res = supabase.table("wrong_questions_selection").select("question_id").eq("user_id", u_id_clean).execute()
            st.session_state.s_wrong_ids = {item["question_id"] for item in res.data}
            st.session_state.db_synced = True
        except:
            pass

# =========================
# 5. サイドバー
# =========================
with st.sidebar:
    st.title("🎯 選択式マスター")
    raw_u_id = st.text_input("ユーザーID", placeholder="ID入力で同期開始")
    u_id = raw_u_id.strip()
    
    if u_id: 
        sync_db(u_id)
        st.caption(f"✅ 同期中: {u_id}")
    
    cat_list = list(questions_dict.keys())
    if not cat_list:
        st.warning("JSONファイルが見つかりません。")
        st.stop()
        
    selected_cat = st.selectbox("科目選択", cat_list)
    
    if selected_cat != st.session_state.current_cat:
        st.session_state.current_cat = selected_cat
        st.session_state.s_index = 0
        st.session_state.s_answered = False
        st.session_state.db_synced = False # 科目変更時も再同期を走らせる場合はここを調整
        st.rerun()
        
    mode = st.radio("学習モード", ["通常学習", "苦手克服 🔥"])

# 問題抽出
target = questions_dict.get(selected_cat, [])
if mode == "苦手克服 🔥":
    target = [q for q in target if q["id"] in st.session_state.s_wrong_ids]

if not target:
    st.info("対象の問題がありません。")
    st.stop()

idx = st.session_state.s_index % len(target)
q = target[idx]

# =========================
# 6. メイン画面
# =========================
st.title(f"📖 {selected_cat}")
st.caption(f"進捗: {idx + 1} / {len(target)}")
st.progress((idx + 1) / len(target))

with st.container(border=True):
    # 空欄記号を強調
    display_q = q["q"].replace("（", " **（ ").replace("）", " ）** ")
    st.markdown(f"### {display_q}")

st.divider()

# --- 解答入力エリア (ラジオボタンに変更) ---
st.write("▼ 各空欄の解答を選択してください")
user_choices = {}

# 空欄(A, B, C...)ごとに横並び、または適宜配置
# 空欄が多い場合は columns を使うと見やすい
cols = st.columns(len(q["options"]))
for i, (label, opts) in enumerate(q["options"].items()):
    with cols[i]:
        user_choices[label] = st.radio(
            f"空欄 【 {label} 】",
            options=opts,
            index=None, # 初期状態は未選択
            key=f"q_{q['id']}_{label}"
        )

# 採点ロジック
if st.button("採点する", use_container_width=True, type="primary") or st.session_state.s_answered:
    # 全ての空欄が選択されているかチェック
    if any(choice is None for choice in user_choices.values()) and not st.session_state.s_answered:
        st.warning("すべての空欄を選択してください。")
    else:
        st.session_state.s_answered = True
        
        # 判定
        results = {label: (user_choices[label] == q["a"][label]) for label in q["a"]}
        all_correct = all(results.values())
        
        if all_correct:
            st.success("🎉 全問正解！")
            if q["id"] in st.session_state.s_wrong_ids:
                st.session_state.s_wrong_ids.remove(q["id"])
                if u_id:
                    supabase.table("wrong_questions_selection").delete().eq("user_id", u_id).eq("question_id", q["id"]).execute()
        else:
            st.error("❌ 不正解が含まれます")
            wrong_labels = [k for k, v in results.items() if not v]
            st.session_state.s_wrong_ids.add(q["id"])
            
            # --- DB保存 (upsertで重複回避) ---
            if u_id:
                try:
                    supabase.table("wrong_questions_selection").upsert({
                        "user_id": u_id,
                        "question_id": int(q["id"]),
                        "category_id": str(selected_cat[:2]),
                        "category_name": str(selected_cat),
                        "wrong_parts": ",".join(wrong_labels)
                    }, on_conflict="user_id,question_id,category_id").execute()
                except Exception as e:
                    st.error(f"DB保存エラー: {e}")
            
            # 正解の明示
            st.markdown("---")
            ans_cols = st.columns(len(q["a"]))
            for i, (l, a) in enumerate(q["a"].items()):
                with ans_cols[i]:
                    color = "green" if results[l] else "red"
                    st.markdown(f"**{l}の正解:**\n:{color}[{a}]")

        # 解説
        with st.expander("💡 解説を確認する", expanded=True):
            st.info(q["tips"])

        if st.button("次の問題へ ➡️", use_container_width=True):
            st.session_state.s_index += 1
            st.session_state.s_answered = False
            st.rerun()

# 統計
st.sidebar.divider()
current_wrong = len([i for i in st.session_state.s_wrong_ids if any(x['id']==i for x in target)])
st.sidebar.metric("この科目の苦手問題", f"{current_wrong} 問")