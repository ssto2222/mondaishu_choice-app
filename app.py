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
if "db_last_index" not in st.session_state: st.session_state.db_last_index = None
if "db_synced" not in st.session_state: st.session_state.db_synced = False
if "app_mode" not in st.session_state: st.session_state.app_mode = "menu"
if "study_filter" not in st.session_state: st.session_state.study_filter = "all" # all or wrong_only

# =========================
# 4. サイドバー
# =========================
with st.sidebar:
    st.title("🎯 選択式マスター")
    raw_u_id = st.text_input("ユーザーID", placeholder="IDを入力してください")
    u_id = raw_u_id.strip()
    
    cat_list = list(questions_dict.keys())
    selected_cat = st.selectbox("科目選択", cat_list)

    if u_id and not st.session_state.db_synced:
        try:
            # 苦手問題の取得
            res_w = supabase.table("wrong_questions_selection").select("question_id").eq("user_id", u_id).execute()
            st.session_state.s_wrong_ids = {item["question_id"] for item in res_w.data}
            
            # 進行状況の取得
            res_p = supabase.table("user_progress").select("last_index").eq("user_id", u_id).eq("category_name", selected_cat).execute()
            st.session_state.db_last_index = res_p.data[0]["last_index"] if res_p.data else None
            
            st.session_state.db_synced = True
        except: pass

    if st.button("メニュー画面へ戻る"):
        st.session_state.app_mode = "menu"
        st.session_state.db_synced = False # 再同期を促す
        st.rerun()

# =========================
# 5. メイン画面：メニュー
# =========================
if st.session_state.app_mode == "menu":
    st.title("📚 学習メニュー")
    st.write(f"現在の科目: **{selected_cat}**")
    
    # 苦手問題のカウント
    current_cat_wrong_count = len([q_id for q_id in st.session_state.s_wrong_ids if any(q['id'] == q_id for q in questions_dict.get(selected_cat, []))])

    col1, col2 = st.columns(2)
    with col1:
        if st.button("最初から解く (全問)", use_container_width=True):
            st.session_state.s_index = 0
            st.session_state.study_filter = "all"
            st.session_state.app_mode = "study"
            st.session_state.s_answered = False
            st.rerun()
            
        # 苦手問題がある場合のみ活性化
        wrong_disabled = current_cat_wrong_count == 0
        if st.button(f"苦手問題のみ挑戦 🔥 ({current_cat_wrong_count}問)", use_container_width=True, disabled=wrong_disabled, type="secondary"):
            st.session_state.s_index = 0
            st.session_state.study_filter = "wrong_only"
            st.session_state.app_mode = "study"
            st.session_state.s_answered = False
            st.rerun()

    with col2:
        resume_disabled = st.session_state.db_last_index is None
        if st.button("前回の続きから再開", use_container_width=True, disabled=resume_disabled, type="primary"):
            st.session_state.s_index = st.session_state.db_last_index
            st.session_state.study_filter = "all"
            st.session_state.app_mode = "study"
            st.session_state.s_answered = False
            st.rerun()

# =========================
# 6. メイン画面：学習モード
# =========================
else:
    all_questions = questions_dict.get(selected_cat, [])
    # フィルタリング
    if st.session_state.study_filter == "wrong_only":
        target = [q for q in all_questions if q["id"] in st.session_state.s_wrong_ids]
    else:
        target = all_questions

    if not target:
        st.warning("対象となる問題がありません。メニューに戻ります。")
        st.session_state.app_mode = "menu"
        st.rerun()

    idx = st.session_state.s_index % len(target)
    q = target[idx]

    st.title(f"📖 {selected_cat} {'(苦手特訓)' if st.session_state.study_filter == 'wrong_only' else ''}")
    st.caption(f"問題: {idx + 1} / {len(target)}")
    st.progress((idx + 1) / len(target))

    with st.container(border=True):
        display_q = q["q"].replace("（", " **（ ").replace("）", " ）** ")
        st.markdown(f"### {display_q}")

    st.divider()

    user_choices = {}
    cols = st.columns(len(q["options"]))
    for i, (label, opts) in enumerate(q["options"].items()):
        with cols[i]:
            user_choices[label] = st.radio(f"空欄 【 {label} 】", options=opts, index=None, key=f"q_{q['id']}_{label}")

    if st.button("採点する", use_container_width=True, type="primary") or st.session_state.s_answered:
        if any(choice is None for choice in user_choices.values()) and not st.session_state.s_answered:
            st.warning("すべての空欄を選択してください。")
        else:
            st.session_state.s_answered = True
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
                
                if u_id:
                    try:
                        supabase.table("wrong_questions_selection").upsert({
                            "user_id": u_id,
                            "question_id": int(q["id"]),
                            "category_id": str(selected_cat[:2]),
                            "category_name": str(selected_cat),
                            "wrong_parts": ",".join(wrong_labels)
                        }, on_conflict="user_id,question_id,category_id").execute()
                    except: pass
                
                # 正解表示
                ans_cols = st.columns(len(q["a"]))
                for i, (l, a) in enumerate(q["a"].items()):
                    with ans_cols[i]:
                        color = "green" if results[l] else "red"
                        st.markdown(f"**{l}の正解:**\n:{color}[{a}]")

            with st.expander("💡 解説を確認する", expanded=True):
                st.info(q["tips"])

            if st.button("次の問題へ ➡️", use_container_width=True):
                st.session_state.s_index += 1
                st.session_state.s_answered = False
                
                # 通常学習モードの時だけ進捗を保存
                if u_id and st.session_state.study_filter == "all":
                    try:
                        supabase.table("user_progress").upsert({
                            "user_id": u_id,
                            "category_name": selected_cat,
                            "last_index": st.session_state.s_index
                        }).execute()
                    except: pass
                
                st.rerun()