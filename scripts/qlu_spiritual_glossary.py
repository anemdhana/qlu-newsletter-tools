"""QLU spiritual vocabulary helpers for Whisper initial prompts."""

from __future__ import annotations

# High-value terms that browser speech often mangles. Keep compact — Whisper
# initial_prompt works best as a short priming paragraph, not a dictionary dump.
GLOSSARY_TE = """
క్వాంటం లైఫ్ యూనివర్సిటీ, జ్ఞానోదయం, డా. న్యూటన్, వన్య మైత్రేయ, గోలోక, సహస్రార,
ఆత్మజ్ఞానం, చైతన్యం, ధ్యానం, శక్తి, కుండలిని, ఆనపానసతి, సత్యం, ధర్మం, కర్మ,
భక్తి, జ్ఞానం, వైరాగ్యం, మోక్షం, సంసారం, అహంకారం, మనస్సు, బుద్ధి, చిత్తం,
జగన్మాత, దేవీ, నవరాత్రి, గణేశుడు, శివుడు, విష్ణువు, కృష్ణుడు, రాముడు,
పురాణం, ఉపనిషత్తు, భగవద్గీత, మంత్రం, యంత్రం, తంత్రం, సేవ, సమర్పణ, సాధన.
""".strip()

GLOSSARY_EN = """
Quantum Life University, Jnanodayam, Dr. Newton, Vanya Maitreya, Goloka, Sahasrara,
Atma Jnana, Chaitanya, Dhyana, Shakti, Kundalini, Anapanasati, Satya, Dharma, Karma,
Bhakti, Jnana, Vairagya, Moksha, Samsara, Ahamkara, Manas, Buddhi, Chitta,
Jaganmata, Devi, Navaratri, Ganesha, Shiva, Vishnu, Krishna, Rama,
Purana, Upanishad, Bhagavad Gita, mantra, yantra, tantra, Seva, Samarpana, Sadhana.
""".strip()

GLOSSARY_HI = """
क्वांटम लाइफ यूनिवर्सिटी, ज्ञानोदयम, डॉ. न्यूटन, वन्य मैत्रेय, गोलोक, सहस्रार,
आत्मज्ञान, चैतन्य, ध्यान, शक्ति, कुण्डलिनी, आनापानसति, सत्य, धर्म, कर्म,
भक्ति, ज्ञान, वैराग्य, मोक्ष, संसार, अहंकार, मन, बुद्धि, चित्त,
जगन्माता, देवी, नवरात्रि, गणेश, शिव, विष्णु, कृष्ण, राम।
""".strip()


def glossary_for_lang(lang: str) -> str:
  code = (lang or "te").lower().split("-")[0]
  if code == "en":
    return GLOSSARY_EN
  if code == "hi":
    return GLOSSARY_HI
  return GLOSSARY_TE


def build_initial_prompt(lang: str, extra: str | None = None) -> str:
  """Short priming text so Whisper prefers QLU spiritual spellings."""
  gloss = glossary_for_lang(lang)
  code = (lang or "te").lower().split("-")[0]
  if code == "en":
    base = (
      "Quantum Life University spiritual lecture. "
      "Preserve Sanskrit and Telugu names accurately. Terms: "
      f"{gloss}"
    )
  elif code == "hi":
    base = (
      "क्वांटम लाइफ यूनिवर्सिटी आध्यात्मिक प्रवचन। "
      "संस्कृत और आध्यात्मिक शब्दों को सही लिखें। शब्द: "
      f"{gloss}"
    )
  else:
    base = (
      "క్వాంటం లైఫ్ యూనివర్సిటీ ఆధ్యాత్మిక ప్రసంగం. "
      "సంస్కృత / తెలుగు ఆధ్యాత్మిక పదాలను సరిగ్గా వ్రాయండి. పదాలు: "
      f"{gloss}"
    )
  extra_clean = (extra or "").strip()
  if extra_clean:
    # Whisper prompt budget is limited; keep extras short.
    base = f"{base} {extra_clean[:240]}"
  # Hard cap ~800 chars to avoid drowning the acoustic model.
  return base[:800]
