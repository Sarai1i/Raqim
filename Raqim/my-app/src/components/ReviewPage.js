import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import { InlineMath, BlockMath } from "react-katex";
import "katex/dist/katex.min.css";
import API_BASE_URL from "../config";

const getWordBox = (word) => word?.bounding_box || word?.boundingBox || null;

// عرض معادلة LaTeX بأمان: يعرضها منسّقة عبر KaTeX، ويرجع للنص الخام لو فشل التحليل.
const MathView = ({ latex, display }) => {
  try {
    return display ? <BlockMath math={latex} /> : <InlineMath math={latex} />;
  } catch (e) {
    return <span className="review-math-fallback">{latex}</span>;
  }
};

const getBoxMetric = (box, key, fallback = 0) => {
  const value = Number(box?.[key]);
  return Number.isFinite(value) ? value : fallback;
};

const getBoxDimension = (box, compactKey, longKey, fallback = 0) => {
  const compactValue = Number(box?.[compactKey]);
  if (Number.isFinite(compactValue) && compactValue > 0) return compactValue;
  const longValue = Number(box?.[longKey]);
  return Number.isFinite(longValue) && longValue > 0 ? longValue : fallback;
};

const median = (values) => {
  const sorted = values.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);
  if (sorted.length === 0) return 18;
  return sorted[Math.floor(sorted.length / 2)];
};

// ترتيب كلمات السطر من اليمين لليسار (أعلى x أولًا) لعرض عربي صحيح.
const sortLineWordsRtl = (entries = []) => {
  return [...entries].sort((a, b) => {
    const ax = getBoxMetric(a.box, "x", 0);
    const bx = getBoxMetric(b.box, "x", 0);
    if (ax !== bx) return bx - ax;
    return a.index - b.index;
  });
};

const lineMetricsFromWords = (entries = []) => {
  const ys = entries.map((entry) => getBoxMetric(entry.box, "y", null)).filter((value) => value !== null);
  const bottoms = entries.map((entry) => {
    const y = getBoxMetric(entry.box, "y", null);
    if (y === null) return null;
    return y + getBoxDimension(entry.box, "h", "height", 0);
  }).filter((value) => value !== null);

  return {
    y: ys.length ? Math.min(...ys) : null,
    bottom: bottoms.length ? Math.max(...bottoms) : null,
    words: sortLineWordsRtl(entries),
  };
};

const groupWordsIntoParagraphs = (words = []) => {
  if (!Array.isArray(words) || words.length === 0) return [];

  const indexedWords = words.map((word, index) => ({ word, index, box: getWordBox(word) }));
  const heights = indexedWords.map(({ box }) => getBoxMetric(box, "h", 0));
  const medianHeight = median(heights);
  const lineTolerance = Math.max(8, medianHeight * 0.72);
  const paragraphGap = Math.max(18, medianHeight * 1.9);

  const hasStructuredLines = indexedWords.some(
    ({ word }) => word?.line_index !== undefined && word?.line_index !== null
  );

  let lines = [];

  if (hasStructuredLines) {
    const lineMap = new Map();
    indexedWords.forEach((entry) => {
      const blockId = entry.word?.block_id ?? 0;
      const lineIndex = entry.word?.line_index ?? 0;
      const key = `${blockId}:${lineIndex}`;
      if (!lineMap.has(key)) lineMap.set(key, []);
      lineMap.get(key).push(entry);
    });

    lines = Array.from(lineMap.entries())
      .sort(([leftKey], [rightKey]) => {
        const [leftBlock, leftLine] = leftKey.split(":").map(Number);
        const [rightBlock, rightLine] = rightKey.split(":").map(Number);
        if (leftBlock !== rightBlock) return leftBlock - rightBlock;
        return leftLine - rightLine;
      })
      .map(([, entries]) => lineMetricsFromWords(entries));
  } else {
    indexedWords.forEach((entry) => {
      const y = getBoxMetric(entry.box, "y", null);
      if (y === null || entry.box === null) {
        const lastLine = lines[lines.length - 1];
        if (!lastLine || lastLine.words.length >= 18) {
          lines.push({ y: null, bottom: null, words: [entry] });
        } else {
          lastLine.words.push(entry);
        }
        return;
      }

      const height = getBoxMetric(entry.box, "h", medianHeight);
      const bottom = y + height;
      const lastLine = lines[lines.length - 1];

      if (lastLine && lastLine.y !== null && Math.abs(y - lastLine.y) <= lineTolerance) {
        const nextCount = lastLine.words.length + 1;
        lastLine.y = ((lastLine.y * lastLine.words.length) + y) / nextCount;
        lastLine.bottom = Math.max(lastLine.bottom || bottom, bottom);
        lastLine.words.push(entry);
      } else {
        lines.push({ y, bottom, words: [entry] });
      }
    });

    lines = lines.map((line) => lineMetricsFromWords(line.words));
  }

  const paragraphs = [];

  lines.forEach((line) => {
    const lastParagraph = paragraphs[paragraphs.length - 1];
    const previousLine = lastParagraph?.lines?.[lastParagraph.lines.length - 1] || null;
    const hasComparableLine = previousLine && previousLine.bottom !== null && previousLine.bottom !== undefined && line.y !== null && line.y !== undefined;
    const gap = hasComparableLine ? line.y - previousLine.bottom : 0;

    if (!lastParagraph || gap > paragraphGap) {
      paragraphs.push({ lines: [line] });
    } else {
      lastParagraph.lines.push(line);
    }
  });

  return paragraphs;
};

const lineToText = (line) => line.words.map(({ word }) => word?.word || "").filter(Boolean).join(" ");

const paragraphsToPlainText = (paragraphs) => {
  return paragraphs
    .map((paragraph) => paragraph.lines.map(lineToText).filter(Boolean).join("\n"))
    .filter(Boolean)
    .join("\n\n");
};

// قسّم الكلمات إلى كتل بالترتيب: كتلة جدول (كلمات لها نفس table_id) أو كتلة نص.
const splitWordsIntoBlocks = (words = []) => {
  const blocks = [];
  let textRun = [];

  const flushText = () => {
    if (textRun.length) {
      blocks.push({ type: "text", words: textRun });
      textRun = [];
    }
  };

  words.forEach((word) => {
    const tableId = word?.table_id ?? null;
    if (tableId !== null && tableId !== undefined) {
      flushText();
      const last = blocks[blocks.length - 1];
      if (last && last.type === "table" && last.tableId === tableId) {
        last.words.push(word);
      } else {
        blocks.push({ type: "table", tableId, words: [word] });
      }
    } else {
      textRun.push(word);
    }
  });

  flushText();
  return blocks;
};

// حوّل كلمات الجدول إلى مصفوفة صفوف [[خلية, ...], ...]
const buildTableRows = (tableWords = []) => {
  const rowsMap = new Map();
  tableWords.forEach((word) => {
    const r = Number(word.table_row) || 0;
    if (!rowsMap.has(r)) rowsMap.set(r, []);
    rowsMap.get(r).push(word);
  });
  return Array.from(rowsMap.keys())
    .sort((a, b) => a - b)
    .map((r) => rowsMap.get(r).sort((a, b) => (Number(a.table_col) || 0) - (Number(b.table_col) || 0)));
};

const ReviewPage = () => {
  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [highlightedBox, setHighlightedBox] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const [selectedWordIndex, setSelectedWordIndex] = useState(null);
  const [correctionProgress, setCorrectionProgress] = useState(0);
  const [totalHighlightedWords, setTotalHighlightedWords] = useState(0);
  const [statusMessage, setStatusMessage] = useState("");
  const [suggestionLoading, setSuggestionLoading] = useState(false);
  const [suggestionError, setSuggestionError] = useState("");
  const [selectedWordInfo, setSelectedWordInfo] = useState(null);
  const [filename, setFilename] = useState("");
  const imageRef = useRef(null);
  const originalPreviewRef = useRef(null);

  useEffect(() => {
    const fetchTextData = async () => {
      try {
        const response = await axios.get(`${API_BASE_URL}/review`);
        const loadedPages = response.data.pages || [];
        setPages(loadedPages);
        setFilename(response.data.original_file || "");

        const reviewableCount = loadedPages.reduce((acc, page) => {
          return acc + (page.text || []).filter((word) => (word.word || "").trim()).length;
        }, 0);
        setTotalHighlightedWords(reviewableCount);
        setCorrectionProgress(0);
      } catch (error) {
        console.error("خطأ في تحميل بيانات المراجعة:", error);
      }
    };

    fetchTextData();
  }, []);

  if (pages.length === 0) {
    return (
      <main className="processing-page" dir="rtl">
        <section className="processing-card">
          <span className="step-pill">المراجعة</span>
          <h1>جاري تحميل النصوص...</h1>
          <p>سنفتح صفحة المقارنة بمجرد أن تكون بيانات الملف جاهزة.</p>
          <div className="loader" aria-label="جاري التحميل"></div>
        </section>
      </main>
    );
  }

  const currentWords = pages[currentPage]?.text || [];
  const currentBlocks = splitWordsIntoBlocks(currentWords);
  const remainingCount = pages.reduce((acc, page) => acc + (page.text || []).filter((word) => (word.word || "").trim() && !word.corrected).length, 0);

  const buildWordContext = (wordIndex) => {
    const start = Math.max(0, wordIndex - 7);
    const end = Math.min(currentWords.length, wordIndex + 8);
    return currentWords.slice(start, end).map((item) => item.word || "").join(" ").trim();
  };

  const normaliseSuggestionItems = (items, originalWord) => {
    const seen = new Set();
    return (items || [])
      .map((item) => {
        if (typeof item === "string") return { word: item };
        return { word: item.word || item.suggestion || item.text || "" };
      })
      .filter((item) => {
        const candidate = item.word.trim();
        if (!candidate || candidate === originalWord || seen.has(candidate)) return false;
        seen.add(candidate);
        return true;
      });
  };

  const updateOriginalHighlight = (wordData, shouldCenter = false) => {
    // تم إيقاف التظليل على الملف الأصلي بناءً على طلب المستخدم.
    // الضغط على الكلمة لا يزال يعمل ويعرض الاقتراحات، لكن لا يظهر أي مربع على الصورة.
    setHighlightedBox(null);
  };

  const fetchSuggestions = async (wordData, event, wordIndex) => {
    const word = wordData.word || "";
    const rect = event.currentTarget.getBoundingClientRect();
    setMenuPosition({
      top: rect.bottom + window.scrollY + 8,
      left: Math.max(16, Math.min(rect.left + window.scrollX, window.innerWidth - 380)),
    });
    setSuggestions([]);
    setSuggestionError("");
    setSuggestionLoading(true);
    setShowSuggestions(true);
    setInputValue(word);
    setSelectedWordIndex(wordIndex);
    setSelectedWordInfo(wordData);

    try {
      const response = await axios.post(`${API_BASE_URL}/get_all_suggestions`, {
        word,
        context: buildWordContext(wordIndex),
        page_number: currentPage + 1,
        word_index: wordIndex,
        max_suggestions: 5,
      });

      const nextSuggestions = normaliseSuggestionItems(response.data.suggestions || [], word);
      setSuggestions(nextSuggestions);
      if (nextSuggestions.length === 0) {
        setSuggestionError(response.data?.message || "الكلمة تبدو صحيحة أو لا توجد اقتراحات مؤكدة. يمكنك تعديلها يدويًا أو اعتمادها كما هي.");
      }
    } catch (error) {
      console.error("خطأ أثناء جلب الاقتراحات:", error);
      setSuggestionError("تعذر تجهيز الاقتراحات الآن. يمكنك المتابعة بالتصحيح اليدوي.");
    } finally {
      setSuggestionLoading(false);
    }
  };

  const handleWordClick = (wordData, event, index) => {
    fetchSuggestions(wordData, event, index);
    updateOriginalHighlight(wordData, true);
  };

  const updateProgress = (pagesToEvaluate = pages) => {
    const correctedCount = pagesToEvaluate.reduce((acc, page) => {
      return acc + (page.text || []).filter((word) => word.corrected).length;
    }, 0);

    if (totalHighlightedWords > 0) {
      const progress = (correctedCount / totalHighlightedWords) * 100;
      setCorrectionProgress(progress);
      setStatusMessage(progress >= 100
        ? "تمت مراجعة جميع كلمات النص. يمكنك تنزيل النص الآن."
        : "يمكنك تنزيل النص في أي وقت أو متابعة مراجعة بقية الكلمات."
      );
    } else {
      setCorrectionProgress(0);
      setStatusMessage("لا توجد كلمات قابلة للمراجعة حالياً.");
    }
  };

  const handleCorrection = async (correction) => {
    if (!correction.trim() || selectedWordIndex === null) return;

    const updatedPages = [...pages];
    const wordData = updatedPages[currentPage].text[selectedWordIndex];
    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      word: correction,
      corrected_word: correction,
      highlighted: false,
      wasHighlighted: Boolean(wordData.highlighted || wordData.wasHighlighted),
      corrected: true,
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();

    try {
      await axios.post(`${API_BASE_URL}/save_correction`, {
        filename,
        original_word: originalWord,
        corrected_word: correction,
        page_number: currentPage + 1,
        word_index: selectedWordIndex,
      });
    } catch (error) {
      console.error("خطأ أثناء حفظ التصحيح:", error);
    }
  };

  const handleMarkCorrect = () => {
    if (selectedWordIndex === null) return;

    const updatedPages = [...pages];
    const wordData = updatedPages[currentPage].text[selectedWordIndex];
    const originalWord = wordData.original_word || wordData.originalWord || wordData.word;

    updatedPages[currentPage].text[selectedWordIndex] = {
      ...wordData,
      original_word: originalWord,
      corrected_word: wordData.word,
      highlighted: false,
      wasHighlighted: Boolean(wordData.highlighted || wordData.wasHighlighted),
      corrected: true,
    };

    setPages(updatedPages);
    setShowSuggestions(false);
    setHighlightedBox(null);
    updateProgress(updatedPages);
    goToNextWord();
  };

  const buildPlainTextFromPages = (pagesToExport = pages) => {
    return pagesToExport
      .map((page) => paragraphsToPlainText(groupWordsIntoParagraphs(page.text || [])))
      .filter(Boolean)
      .join("\n\n");
  };

  const buildCorrectionsPayload = (pagesToSubmit = pages) => {
    return pagesToSubmit.map((page, pageIndex) => ({
      page_number: page.page_number || pageIndex + 1,
      text: (page.text || []).map((word, wordIndex) => {
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
      await axios.post(`${API_BASE_URL}/submit_corrections`, {
        filename,
        corrections: buildCorrectionsPayload(pagesToSubmit),
      });
    } catch (error) {
      console.warn("لم يتم حفظ كل التصحيحات دفعة واحدة، وسيتم تنزيل النص من حالة الواجهة الحالية:", error);
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

    setStatusMessage("تم تنزيل النص حسب التصحيحات الحالية، ويمكنك الاستمرار في المراجعة إذا رغبت.");
  };

  const handleDownloadWord = async () => {
    // نحفظ التصحيحات أولًا حتى يبني الخادم ملف Word من آخر حالة محدثة.
    await submitCorrectionsToServer(pages);
    const link = document.createElement("a");
    link.href = `${API_BASE_URL}/download_corrected_docx`;
    link.download = "raqeim_corrected_text.docx";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setStatusMessage("يتم تنزيل ملف Word حسب التصحيحات الحالية.");
  };

  const goToNextWord = () => {
    if (!pages[currentPage]?.text) return;
    let nextIndex = (selectedWordIndex ?? -1) + 1;
    while (nextIndex < pages[currentPage].text.length && !(pages[currentPage].text[nextIndex].word || "").trim()) {
      nextIndex++;
    }

    if (nextIndex < pages[currentPage].text.length) {
      setSelectedWordIndex(nextIndex);
      setShowSuggestions(false);
    } else {
      goToNextPage();
    }
  };

  const goToNextPage = () => {
    if (currentPage < pages.length - 1) {
      const nextPageIndex = currentPage + 1;
      const firstReviewableIndex = pages[nextPageIndex]?.text?.findIndex((word) => (word.word || "").trim() && !word.corrected) ?? -1;
      setCurrentPage(nextPageIndex);
      setSelectedWordIndex(firstReviewableIndex >= 0 ? firstReviewableIndex : null);
      setShowSuggestions(false);
      setHighlightedBox(null);
    }
  };

  const goToPreviousPage = () => {
    if (currentPage > 0) {
      setCurrentPage(currentPage - 1);
      setSelectedWordIndex(null);
      setShowSuggestions(false);
      setHighlightedBox(null);
    }
  };

  const progressLabel = correctionProgress === 0
    ? "0%"
    : correctionProgress < 1
      ? `${correctionProgress.toFixed(1)}%`
      : `${Math.round(correctionProgress)}%`;
  const progressWidth = correctionProgress > 0 ? `${Math.min(100, correctionProgress)}%` : "0%";

  return (
    <main className="review-page" dir="rtl">
      <header className="review-topbar">
        <div>
          <span className="step-pill">المراجعة اليدوية</span>
          <h1>قارن الملف الأصلي بالنص المستخرج</h1>
          <p>الكلمات التي تحتاج إلى انتباهك مظللة داخل النص، ويمكنك الضغط على أي كلمة في النص لعرض اقتراحات التصحيح بجانبها.</p>
        </div>
        <button className="rq-button rq-button--primary" onClick={handleDownloadCorrectedText}>تنزيل النص الحالي</button>
        <button className="rq-button rq-button--secondary" onClick={handleDownloadWord}>تنزيل Word</button>
      </header>

      <section className="review-progress-card">
        <div className="review-progress-copy">
          <strong>تقدم المراجعة</strong>
          <span>{statusMessage || "ابدأ بالضغط على أي كلمة في النص لمراجعتها."}</span>
        </div>
        <div className="review-progress-track" aria-label={`نسبة التقدم ${progressLabel}`}>
          <div className="review-progress-fill" style={{ width: progressWidth }}>
            {correctionProgress > 0 ? progressLabel : ""}
          </div>
        </div>
        <span className="review-progress-value">{progressLabel}</span>
        <span className="remaining-pill">{remainingCount} كلمة متبقية للمراجعة</span>
      </section>

      <section className="review-workspace">
        <article className="review-panel review-panel--original">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">الملف الأصلي</span>
              <h2>معاينة الصفحة</h2>
            </div>
            <span className="page-chip">{currentPage + 1} / {pages.length}</span>
          </div>
          <div
            className="original-preview"
            ref={originalPreviewRef}
            onScroll={() => {
              if (selectedWordInfo) updateOriginalHighlight(selectedWordInfo);
            }}
          >
            <div className="original-image-wrapper">
              <img
                ref={imageRef}
                src={`${API_BASE_URL}/uploads/original_page_${currentPage + 1}.png`}
                alt="معاينة الصفحة الأصلية"
                className="original-image"
                onLoad={() => {
                  if (selectedWordInfo) updateOriginalHighlight(selectedWordInfo);
                }}
              />
              {highlightedBox && (
                <div
                  className="original-word-marker"
                  style={{
                    top: highlightedBox.top,
                    left: highlightedBox.left,
                    width: highlightedBox.width,
                    height: highlightedBox.height,
                  }}
                />
              )}
            </div>
          </div>
        </article>

        <article className="review-panel review-panel--text">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">النص المستخرج</span>
              <h2>اضغط على الكلمة للمراجعة</h2>
            </div>
            <span className="legend-dot"><i></i> كلمات تحتاج انتباه</span>
          </div>

          <div className="extracted-text" dir="rtl" onClick={(event) => event.stopPropagation()}>
            {currentBlocks.map((block, blockIndex) => {
              if (block.type === "table") {
                const rows = buildTableRows(block.words);
                return (
                  <table className="review-table" key={`block-${blockIndex}-table`}>
                    <tbody>
                      {rows.map((cells, rowIndex) => (
                        <tr key={`block-${blockIndex}-row-${rowIndex}`}>
                          {cells.map((word) => {
                            const isSelected = selectedWordIndex === word.index && showSuggestions;
                            const cellClass = [
                              "review-table-cell",
                              word.highlighted ? "review-word--flagged" : "",
                              word.corrected ? "review-word--corrected" : "",
                              isSelected ? "review-word--selected" : "",
                            ].filter(Boolean).join(" ");
                            return (
                              <td
                                key={word.index}
                                className={cellClass}
                                rowSpan={Number(word.table_rowspan) > 1 ? Number(word.table_rowspan) : undefined}
                                colSpan={Number(word.table_colspan) > 1 ? Number(word.table_colspan) : undefined}
                                onClick={(event) => handleWordClick(word, event, word.index)}
                                title={word.highlighted ? "خلية تحتاج مراجعة" : "اضغط للمراجعة"}
                              >
                                {word.word}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              }

              // كتلة نص عادية
              const paragraphs = groupWordsIntoParagraphs(block.words);
              return paragraphs.map((paragraph, paragraphIndex) => (
                <p className="review-paragraph" key={`block-${blockIndex}-paragraph-${paragraphIndex}`}>
                  {paragraph.lines.map((line, lineIndex) => (
                    <span className="review-line" key={`block-${blockIndex}-p-${paragraphIndex}-line-${lineIndex}`}>
                      {line.words.map(({ word, index }) => {
                        const isSelected = selectedWordIndex === index && showSuggestions;

                        // كلمة معادلة: نعرضها منسّقة عبر KaTeX (تبقى قابلة للنقر للتصحيح).
                        if (word.is_math) {
                          return (
                            <React.Fragment key={index}>
                              <span
                                className={`review-math${isSelected ? " review-word--selected" : ""}`}
                                onClick={(event) => handleWordClick(word, event, index)}
                                title="معادلة — اضغط للمراجعة"
                              >
                                <MathView latex={word.latex || word.word} display={word.math_display} />
                              </span>{" "}
                            </React.Fragment>
                          );
                        }

                        const className = [
                          "review-word",
                          word.highlighted ? "review-word--flagged" : "",
                          word.corrected ? "review-word--corrected" : "",
                          isSelected ? "review-word--selected" : "",
                        ].filter(Boolean).join(" ");

                        return (
                          <React.Fragment key={index}>
                            <span
                              className={className}
                              onClick={(event) => handleWordClick(word, event, index)}
                              title={word.highlighted ? "كلمة تحتاج مراجعة" : "اضغط للمراجعة"}
                            >
                              {word.word}
                            </span>{" "}
                          </React.Fragment>
                        );
                      })}
                    </span>
                  ))}
                </p>
              ));
            })}
          </div>
        </article>
      </section>

      {showSuggestions && (
        <aside className="word-suggestions-menu" style={{ top: menuPosition.top, left: menuPosition.left }} dir="rtl">
          <div className="suggestions-head">
            <div>
              <span>الكلمة الحالية</span>
              <strong>{selectedWordInfo?.word || inputValue}</strong>
            </div>
            <button className="suggestions-close" onClick={() => setShowSuggestions(false)} aria-label="إغلاق الاقتراحات">×</button>
          </div>

          <div className="suggestions-section">
            <span className="suggestions-label">اقتراحات التصحيح</span>
            {suggestionLoading && <div className="suggestions-state">جاري تجهيز الاقتراحات...</div>}
            {!suggestionLoading && suggestions.map((suggestion, idx) => {
              const suggestionWord = typeof suggestion === "string" ? suggestion : suggestion.word;
              return (
                <button
                  key={idx}
                  className="suggestion-option"
                  type="button"
                  onClick={() => setInputValue(suggestionWord)}
                >
                  {suggestionWord}
                </button>
              );
            })}
            {!suggestionLoading && suggestionError && <div className="suggestions-state">{suggestionError}</div>}
          </div>

          <label className="manual-correction-field">
            <span>تصحيح يدوي</span>
            <input value={inputValue} onChange={(e) => setInputValue(e.target.value)} placeholder="اكتب التصحيح هنا" />
          </label>

          <div className="suggestions-actions">
            <button className="rq-button rq-button--primary" onClick={() => handleCorrection(inputValue)}>اعتماد التصحيح</button>
            <button className="rq-button rq-button--ghost" onClick={handleMarkCorrect}>الكلمة صحيحة</button>
          </div>
        </aside>
      )}

      <nav className="review-pagination" aria-label="التنقل بين الصفحات">
        <button className="rq-button rq-button--secondary" onClick={goToPreviousPage} disabled={currentPage === 0}>الصفحة السابقة</button>
        <span>الصفحة {currentPage + 1} من {pages.length}</span>
        <button className="rq-button rq-button--secondary" onClick={goToNextPage} disabled={currentPage === pages.length - 1}>الصفحة التالية</button>
      </nav>
    </main>
  );
};

export default ReviewPage;