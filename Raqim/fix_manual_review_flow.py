from pathlib import Path

review_path = Path('/home/ubuntu/Raqim/my-app/src/components/ReviewPage.js')
app_path = Path('/home/ubuntu/Raqim/my-app/src/App.js')
backend_path = Path('/home/ubuntu/Raqim/Backend/app.py')

text = review_path.read_text(encoding='utf-8')

# Remove unused navigation dependency and state for forced download page.
text = text.replace('import { useNavigate } from "react-router-dom";\n', '')
text = text.replace('\n  const navigate = useNavigate();\n', '\n')
text = text.replace('  const [, setCorrectedHighlightedWords] = useState(0);\n', '  const [statusMessage, setStatusMessage] = useState("");\n')

# Replace progress updater so it can evaluate freshly updated pages and never navigates automatically.
old_update = '''  const updateProgress = () => {
    const correctedCount = pages.reduce((acc, page) => {
      return acc + page.text.filter(word => word.corrected && word.wasHighlighted).length;
    }, 0);

    setCorrectedHighlightedWords(correctedCount);

    if (totalHighlightedWords > 0) {
      const progress = Math.round((correctedCount / totalHighlightedWords) * 100);
      setCorrectionProgress(progress);

      if (progress === 100) {
        submitCorrectionsToServer().then(() => {
          navigate("/download");
        });
      }
    } else {
      setCorrectionProgress(100);
    }
  };
'''
new_update = '''  const updateProgress = (pagesToEvaluate = pages) => {
    const correctedCount = pagesToEvaluate.reduce((acc, page) => {
      return acc + page.text.filter(word => word.corrected && word.wasHighlighted).length;
    }, 0);

    if (totalHighlightedWords > 0) {
      const progress = Math.round((correctedCount / totalHighlightedWords) * 100);
      setCorrectionProgress(progress);

      if (progress === 100) {
        setStatusMessage("تمت مراجعة جميع الكلمات المقترحة. يمكنك تنزيل الملف الآن أو البقاء في الصفحة للمراجعة.");
      } else {
        setStatusMessage("يمكنك تنزيل الملف المصحح في أي وقت، أو إكمال مراجعة الكلمات المتبقية.");
      }
    } else {
      setCorrectionProgress(100);
      setStatusMessage("لا توجد كلمات منخفضة الثقة. يمكنك تنزيل النص كما هو أو مراجعته يدويًا.");
    }
  };
'''
if old_update not in text:
    raise SystemExit('Could not find old updateProgress block')
text = text.replace(old_update, new_update)

# Fix handleCorrection to preserve the original OCR token and update progress from the fresh state.
old_corr = '''    // تحديث النص المصحح في الواجهة الأمامية
    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      word: correction,
      highlighted: false,
      wasHighlighted: true,
      corrected: true
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress();
    goToNextWord();
'''
new_corr = '''    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    // تحديث النص المصحح في الواجهة الأمامية مع الاحتفاظ بالكلمة الأصلية لاستخدامها عند الحفظ.
    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      word: correction,
      corrected_word: correction,
      highlighted: false,
      wasHighlighted: true,
      corrected: true
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();
'''
if old_corr not in text:
    raise SystemExit('Could not find correction update block')
text = text.replace(old_corr, new_corr)
text = text.replace('        original_word: wordData.word,', '        original_word: originalWord,')

# Fix mark-correct to keep current word as corrected and avoid stale progress.
old_mark = '''    const updatedPages = [...pages];
    updatedPages[currentPage].text[selectedWordIndex] = {
      ...updatedPages[currentPage].text[selectedWordIndex],
      highlighted: false,
      wasHighlighted: true,
      corrected: true
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress();
    goToNextWord();
  };
'''
new_mark = '''    const updatedPages = [...pages];
    const wordData = updatedPages[currentPage].text[selectedWordIndex];
    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      corrected_word: wordData.word,
      highlighted: false,
      wasHighlighted: true,
      corrected: true
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();
  };
'''
if old_mark not in text:
    raise SystemExit('Could not find mark correct block')
text = text.replace(old_mark, new_mark)

# Replace bulk submit with normalized payload and add client-side TXT download that reflects current page state.
old_submit = '''  const submitCorrectionsToServer = async () => {
    try {
      const response = await axios.post(`${API_BASE_URL}/submit_corrections`, {
        corrections: pages
      });
      console.log("✅ التصحيحات تم إرسالها بنجاح:", response.data);
    } catch (error) {
      console.error("❌ خطأ أثناء إرسال التصحيحات:", error);
    }
  };
'''
new_submit = '''  const buildPlainTextFromPages = (pagesToExport = pages) => {
    return pagesToExport
      .map((page) => page.text.map((word) => word.word || "").join(" ").trim())
      .filter(Boolean)
      .join("\\n\\n");
  };

  const buildCorrectionsPayload = (pagesToSubmit = pages) => {
    return pagesToSubmit.map((page, pageIndex) => ({
      page_number: page.page_number || pageIndex + 1,
      text: page.text.map((word, wordIndex) => {
        const originalWord = word.original_word || word.originalWord || word.word;
        const correctedWord = word.corrected_word || (word.corrected ? word.word : "");
        return {
          index: word.index ?? wordIndex,
          word: originalWord,
          corrected_word: correctedWord,
        };
      }),
    }));
  };

  const submitCorrectionsToServer = async (pagesToSubmit = pages) => {
    if (!filename) return;

    try {
      const response = await axios.post(`${API_BASE_URL}/submit_corrections`, {
        filename,
        corrections: buildCorrectionsPayload(pagesToSubmit),
      });
      console.log("✅ التصحيحات تم إرسالها بنجاح:", response.data);
    } catch (error) {
      console.warn("⚠️ لم يتم حفظ كل التصحيحات دفعة واحدة، وسيتم تنزيل النص من حالة الواجهة الحالية:", error);
    }
  };

  const handleDownloadCorrectedText = async () => {
    await submitCorrectionsToServer(pages);

    const correctedText = buildPlainTextFromPages(pages);
    const blob = new Blob([correctedText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "raqeim_manual_corrected_text.txt";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setStatusMessage("تم تنزيل الملف النصي حسب التصحيحات الحالية. يمكنك الاستمرار في المراجعة إذا رغبت.");
  };
'''
if old_submit not in text:
    raise SystemExit('Could not find submitCorrectionsToServer block')
text = text.replace(old_submit, new_submit)

# Improve next page behavior: move to first highlighted word if possible.
text = text.replace('''      setCurrentPage(currentPage + 1);
      setSelectedWordIndex(0);
      setShowSuggestions(false);''', '''      const nextPageIndex = currentPage + 1;
      const firstHighlightedIndex = pages[nextPageIndex]?.text?.findIndex((word) => word.highlighted) ?? -1;
      setCurrentPage(nextPageIndex);
      setSelectedWordIndex(firstHighlightedIndex >= 0 ? firstHighlightedIndex : 0);
      setShowSuggestions(false);''')

# Insert action panel after progress bar.
old_panel_anchor = '''</div>



      <div style={styles.splitView}>'''
new_panel_anchor = '''</div>

      <div style={styles.reviewActions}>
        <div style={styles.reviewHint}>
          <strong>التنزيل اختياري:</strong> تستطيع تنزيل الملف المصحح الآن حتى لو بقيت كلمات لم تراجعها، أو تكمل المراجعة ثم تنزله لاحقًا.
          {statusMessage && <span style={styles.statusMessage}>{statusMessage}</span>}
        </div>
        <button style={styles.downloadButton} onClick={handleDownloadCorrectedText}>
          تنزيل النص المصحح الحالي TXT
        </button>
      </div>

      <div style={styles.splitView}>'''
if old_panel_anchor not in text:
    raise SystemExit('Could not find panel anchor')
text = text.replace(old_panel_anchor, new_panel_anchor)

# Add action styles before splitView.
style_anchor = '''  splitView: {
    display: "flex",'''
new_styles = '''  reviewActions: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "18px",
    background: "#ffffff",
    border: "1px solid rgba(0, 33, 71, 0.08)",
    borderRadius: "14px",
    padding: "16px 20px",
    boxShadow: "0 8px 22px rgba(2, 32, 71, 0.08)",
    marginBottom: "18px",
    textAlign: "right",
  },
  reviewHint: {
    color: "#2d3748",
    lineHeight: 1.8,
    flex: 1,
  },
  statusMessage: {
    display: "block",
    marginTop: "4px",
    color: "#0b4f7a",
    fontWeight: 700,
  },
  downloadButton: {
    padding: "12px 20px",
    borderRadius: "999px",
    border: "none",
    backgroundColor: "#002147",
    color: "#fff",
    fontWeight: 700,
    cursor: "pointer",
    fontFamily: "IBM Plex Sans Arabic, sans-serif",
    whiteSpace: "nowrap",
  },
  splitView: {
    display: "flex",'''
if style_anchor not in text:
    raise SystemExit('Could not find style anchor')
text = text.replace(style_anchor, new_styles)

review_path.write_text(text, encoding='utf-8')

# Remove missing DownloadPage import and route to avoid forced navigation/build failure.
app_text = app_path.read_text(encoding='utf-8')
app_text = app_text.replace('import DownloadPage from "./components/DownloadPage";\n', '')
app_text = app_text.replace('        <Route path="/download" element={<DownloadPage />} />\n', '')
app_path.write_text(app_text, encoding='utf-8')

# Fix backend GET /download_corrected as a fallback: apply saved corrections to OCR words.
backend = backend_path.read_text(encoding='utf-8')
old_backend_download = '''@app.route("/download_corrected", methods=["GET"])
def download_corrected():
    """تنزيل النص المصحح"""
    global ocr_results

    if not ocr_results:
        return jsonify({"error": "❌ لا توجد نتائج OCR متاحة!"}), 404

    # تجميع النص المصحح
    corrected_text = []
    for page in ocr_results:
        page_text = " ".join([word["word"] for word in page.get("text", [])])  # تجميع النص كسطر واحد لكل صفحة
        corrected_text.append(page_text)

    # كتابة النص المصحح إلى ملف
    with open(corrected_text_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(corrected_text))

    # إرسال الملف للتنزيل
    return send_file(corrected_text_file, as_attachment=True, download_name="corrected_text.txt", mimetype="text/plain")
'''
new_backend_download = '''@app.route("/download_corrected", methods=["GET"])
def download_corrected():
    """تنزيل النص المصحح مع تطبيق التصحيحات المحفوظة يدويًا إن وجدت."""
    global ocr_results, original_file_name

    if not ocr_results:
        return jsonify({"error": "❌ لا توجد نتائج OCR متاحة!"}), 404

    filename = request.args.get("filename") or original_file_name
    saved_corrections = {}
    if filename:
        for correction in corrected_words_collection.find({"filename": filename}, {"_id": 0}):
            key = (correction.get("page_number"), correction.get("word_index"))
            saved_corrections[key] = correction.get("corrected_word", "")

    corrected_text = []
    for page_index, page in enumerate(ocr_results, start=1):
        page_words = []
        for word_index, word in enumerate(page.get("text", [])):
            replacement = saved_corrections.get((page_index, word_index))
            page_words.append(replacement or word.get("word", ""))
        corrected_text.append(" ".join(page_words).strip())

    with open(corrected_text_file, "w", encoding="utf-8") as f:
        f.write("\n\n".join(corrected_text))

    return send_file(corrected_text_file, as_attachment=True, download_name="corrected_text.txt", mimetype="text/plain")
'''
if old_backend_download in backend:
    backend = backend.replace(old_backend_download, new_backend_download)
else:
    print('Backend download block not replaced; it may already be updated.')
backend_path.write_text(backend, encoding='utf-8')
