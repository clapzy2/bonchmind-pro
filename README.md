# BonchMind Pro

BonchMind Pro — RAG-система для работы с учебными материалами.  
Преподаватель загружает документы, а студенты задают вопросы и получают ответы с цитатами из источников.

## Возможности

- загрузка PDF, DOCX, TXT, EPUB, FB2, HTML и Markdown;
- автоматическая индексация документов;
- поиск по смыслу через BGE-M3;
- реранжирование найденных фрагментов;
- ответы с цитатами;
- фильтрация по файлу и разделу;
- работа через OpenRouter API или локально через Ollama;
- веб-интерфейс на Gradio.

## Архитектура

Пользовательский вопрос проходит несколько этапов:

1. HyDE-переформулировка запроса;
2. преобразование запроса в эмбеддинг;
3. поиск релевантных фрагментов в ChromaDB;
4. реранжирование через cross-encoder;
5. генерация ответа через LLM.

## Стек

- Python
- Gradio
- ChromaDB
- Sentence-Transformers
- BGE-M3
- BGE-Reranker-v2-m3
- Qwen3
- Ollama
- OpenRouter

## Установка

```bash
git clone https://github.com/clapzy2/bonchmind-pro.git
cd bonchmind-pro
python -m venv .venv