#!/bin/bash
# Downloads the SPLAIM local-RAG document corpus (open-access arXiv PDFs)
cd "$(dirname "$0")/data" || exit 1

# filename|arxiv_id
papers=(
  "rag_lewis_2020.pdf|2005.11401"
  "rag_survey_gao_2023.pdf|2312.10997"
  "qlora_dettmers_2023.pdf|2305.14314"
  "llm_int8_dettmers_2022.pdf|2208.07339"
  "gptq_frantar_2022.pdf|2210.17323"
  "extracting_training_data_carlini_2021.pdf|2012.07805"
)

for entry in "${papers[@]}"; do
  name="${entry%%|*}"
  id="${entry##*|}"
  echo "Downloading $name (arXiv:$id) ..."
  curl -sL -A "Mozilla/5.0" "https://arxiv.org/pdf/$id" -o "$name"
  sleep 2   # be polite to arXiv
done

echo ""
echo "===== VERIFY (each should say 'PDF document') ====="
for entry in "${papers[@]}"; do
  name="${entry%%|*}"
  if [ -f "$name" ]; then
    printf "%-45s " "$name"
    file "$name" | grep -q "PDF" && echo "OK ($(du -h "$name" | cut -f1))" || echo "NOT A PDF — download failed"
  else
    echo "$name  MISSING"
  fi
done
