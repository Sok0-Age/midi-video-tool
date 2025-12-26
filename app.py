import streamlit as st
import mido
import cv2
import tempfile
import os
import numpy as np

st.title("MIDI同期動画ジェネレーター")

# ------ ファイルアップロード ------
midi_file = st.file_uploader("MIDIファイルをアップロード", type=["mid", "midi"])
video_file = st.file_uploader("動画ファイルをアップロード", type=["mp4", "mov", "avi"])

# ------------------------------------------------------------
#  MIDI アップロード → temp に保存 → BPM表示 → トラック選択
# ------------------------------------------------------------

if midi_file:
    # ---- 必ず最初に「保存」してから読む ----
    temp_midi = tempfile.NamedTemporaryFile(delete=False, suffix=".mid")
    temp_midi.write(midi_file.getbuffer())
    temp_midi.close()

    midi = mido.MidiFile(temp_midi.name)
    ticks_per_beat = midi.ticks_per_beat

    # ---- BPM算出 ----
    tempo = None
    for track in midi.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo = msg.tempo
                break
        if tempo is not None:
            break

    if tempo is None:
        tempo = 500000  # デフォルト 120 BPM

    bpm = mido.tempo2bpm(tempo)

    # 🎉 ここに BPM が表示される！
    st.subheader(f"推定 BPM：**{bpm:.2f} BPM**")

    # ---- トラック選択（ノート数つき） ----
    track_options = []
    for i, track in enumerate(midi.tracks):
        note_count = sum(1 for msg in track if msg.type ==
                         "note_on" and msg.velocity > 0)

        name = None
        for msg in track:
            if msg.type == "track_name":
                name = msg.name
                break

        track_options.append(
            f"{i}: {name if name else '名前なし'}（ノート数: {note_count}）")

    selected_track_name = st.selectbox("処理するトラックを選択", track_options)
    selected_track_index = int(selected_track_name.split(":")[0])

    # ---- ノート解析 ----
    if st.button("選択トラックのノートを解析"):

        tempo = 500000
        current_time = 0
        note_times = []

        for msg in midi.tracks[selected_track_index]:
            current_time += mido.tick2second(msg.time, ticks_per_beat, tempo)
            if msg.type == "set_tempo":
                tempo = msg.tempo
            if msg.type == "note_on" and msg.velocity > 0:
                note_times.append(current_time)

        st.success(f"ノート数: {len(note_times)}")
        st.session_state["note_times"] = note_times
        st.session_state["midi_loaded"] = True


# ------------------------------------------------------------
#  動画アップロード後の処理
# ------------------------------------------------------------

if video_file and st.session_state.get("midi_loaded"):

    # ---- 同様に video も最初に保存する ----
    temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    temp_video.write(video_file.getbuffer())
    temp_video.close()

    # プレビュー
    st.subheader("アップロード動画プレビュー")
    st.video(video_file)

    loop_video = st.checkbox("動画をループしてノート数分再生する")

    flip_mode = st.selectbox(
        "左右反転モード",
        ["反転しない", "毎ノート交互に反転", "毎ノート反転", "ランダム反転"]
    )

    if st.button("動画を生成（ノート間ずっと表示・反転対応）"):

        temp_video = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
        temp_video.write(video_file.getbuffer())
        temp_video.close()

        cap = cv2.VideoCapture(temp_video.name)
        fps = cap.get(cv2.CAP_PROP_FPS)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        out_path = tempfile.NamedTemporaryFile(
            delete=False, suffix=".mp4").name
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(out_path, fourcc, fps, (w, h))

        note_times = st.session_state["note_times"]
        st.info("動画生成中…")

        extended_times = note_times + [note_times[-1] + 1.0]

        import random

        for i in range(len(note_times)):

            start_t = extended_times[i]
            end_t = extended_times[i+1]

            duration = end_t - start_t
            frames_to_write = int(duration * fps)

            # --- ▼▼ 反転するか判定 ▼▼ ---
            flip = False
            if flip_mode == "毎ノート反転":
                flip = True
            elif flip_mode == "毎ノート交互に反転":
                flip = (i % 2 == 1)
            elif flip_mode == "ランダム反転":
                flip = random.choice([True, False])
            # ----------------------------------

            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            for _ in range(frames_to_write):
                ret, frame = cap.read()
                if not ret:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ret, frame = cap.read()

                # --- ▼▼ 反転処理本体 ▼▼ ---
                if flip:
                    frame = cv2.flip(frame, 1)
                # ---------------------------

                out.write(frame)

        cap.release()
        out.release()

        st.success("動画生成完了！（反転モード対応）")
        st.video(out_path)

        with open(out_path, "rb") as f:
            st.download_button("動画をダウンロード", f, file_name="output.mp4")
