import streamlit as st
import openai

st.set_page_config(page_title="카드뉴스 자동 생성기", page_icon="📱", layout="centered")

st.title("📱 AI 카드뉴스 & 이미지 생성기")
st.write("뉴스 기사나 내용을 입력하면 카드뉴스 기획안과 AI 이미지를 생성합니다.")

api_key = st.sidebar.text_input("OpenAI API Key 입력", type="password")

if not api_key:
    st.info("시작하려면 사이드바에 OpenAI API Key를 입력해주세요.")
    st.stop()

client = openai.OpenAI(api_key=api_key)

news_content = st.text_area("뉴스 기사 내용 또는 요약 텍스트를 입력하세요:", height=200)

if st.button("🚀 카드뉴스 & 이미지 생성하기", use_container_width=True):
    if not news_content.strip():
        st.warning("뉴스 내용을 입력해주세요!")
        st.stop()

    with st.spinner("1/2. AI가 뉴스 기사를 분석하여 카드뉴스 기획안을 작성 중입니다..."):
        prompt_text = f"""
너는 인스타그램 카드뉴스 전문가야. 아래 뉴스 내용을 바탕으로 인스타그램 카드뉴스 기획안을 작성해줘.

[뉴스 내용]
{news_content}

[작성 지침]
1. 카드뉴스는 총 8장(1:1 비율) 구성으로 작성해줘.
   - 1장: 강력한 후킹 헤드라인 (표지) 및 이미지 묘사
   - 2~7장: 사건의 주요 내용 요약 (각 장당 3줄 이내)
   - 8장: 독자 참여 유도 (댓글, 공유 CTA)
2. 인스타그램 캡션 본문 작성
   - 공감형/투표유도형 톤앤매너
   - 관련 해시태그 10개 포함
3. DALL-E 3용 대표 이미지 영어 프롬프트 1개
   - "DALL-E Prompt:" 뒤에 한 문장의 정교한 영어 프롬프트만 적어줘. (1:1 비율, 실사 스타일)
        """

        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt_text}],
                temperature=0.7
            )
            result_text = response.choices[0].message.content
        except Exception as e:
            st.error(f"텍스트 생성 중 오류가 발생했습니다: {e}")
            st.stop()

    image_prompt = ""
    for line in result_text.split("\n"):
        if "DALL-E Prompt:" in line:
            image_prompt = line.replace("DALL-E Prompt:", "").strip()
            break
    
    if not image_prompt:
        image_prompt = f"A photorealistic news illustration related to: {news_content[:100]}, cinematic lighting, high detail, 1:1 aspect ratio"

    with st.spinner("2/2. 뉴스 내용에 맞는 대표 AI 이미지를 생성 중입니다..."):
        try:
            img_response = client.images.generate(
                model="dall-e-3",
                prompt=image_prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = img_response.data[0].url
        except Exception as e:
            st.error(f"이미지 생성 중 오류가 발생했습니다: {e}")
            image_url = None

    st.success("✨ 카드뉴스 생성 완료!")
    
    if image_url:
        st.subheader("🖼️ 대표 AI 이미지 (1장)")
        st.image(image_url, caption="생성된 카드뉴스 표지/배경 이미지", use_container_width=True)
        st.write(f"**사용한 DALL-E 프롬프트:** `{image_prompt}`")

    st.subheader("📝 카드뉴스 기획 및 본문 내용")
    st.markdown(result_text)
