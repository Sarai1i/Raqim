from pathlib import Path

review_path = Path('/home/ubuntu/Raqim/my-app/src/components/ReviewPage.js')
css_path = Path('/home/ubuntu/Raqim/my-app/src/App.css')

review = review_path.read_text()

review = review.replace(
    'import React, { useEffect, useRef, useState } from "react";\n',
    'import React, { useEffect, useRef, useState } from "react";\n'
)

helpers = '''\nconst getWordBox = (word) => word?.bounding_box || word?.boundingBox || null;\n\nconst getBoxMetric = (box, key, fallback = 0) => {\n  const value = Number(box?.[key]);\n  return Number.isFinite(value) ? value : fallback;\n};\n\nconst median = (values) => {\n  const sorted = values.filter((value) => Number.isFinite(value) && value > 0).sort((a, b) => a - b);\n  if (sorted.length === 0) return 18;\n  return sorted[Math.floor(sorted.length / 2)];\n};\n\nconst groupWordsIntoParagraphs = (words = []) => {\n  if (!Array.isArray(words) || words.length === 0) return [];\n\n  const indexedWords = words.map((word, index) => ({ word, index, box: getWordBox(word) }));\n  const heights = indexedWords.map(({ box }) => getBoxMetric(box, \"h\", 0));\n  const medianHeight = median(heights);\n  const lineTolerance = Math.max(8, medianHeight * 0.72);\n  const paragraphGap = Math.max(18, medianHeight * 1.9);\n\n  const lines = [];\n\n  indexedWords.forEach((entry) => {\n    const y = getBoxMetric(entry.box, \"y\", null);\n    if (y === null || entry.box === null) {\n      const lastLine = lines[lines.length - 1];\n      if (!lastLine || lastLine.words.length >= 18) {\n        lines.push({ y: null, bottom: null, words: [entry] });\n      } else {\n        lastLine.words.push(entry);\n      }\n      return;\n    }\n\n    const height = getBoxMetric(entry.box, \"h\", medianHeight);\n    const bottom = y + height;\n    const lastLine = lines[lines.length - 1];\n\n    if (lastLine && lastLine.y !== null && Math.abs(y - lastLine.y) <= lineTolerance) {\n      const nextCount = lastLine.words.length + 1;\n      lastLine.y = ((lastLine.y * lastLine.words.length) + y) / nextCount;\n      lastLine.bottom = Math.max(lastLine.bottom || bottom, bottom);\n      lastLine.words.push(entry);\n    } else {\n      lines.push({ y, bottom, words: [entry] });\n    }\n  });\n\n  const paragraphs = [];\n\n  lines.forEach((line) => {\n    const lastParagraph = paragraphs[paragraphs.length - 1];\n    const previousLine = lastParagraph?.lines?.[lastParagraph.lines.length - 1];\n    const gap = previousLine?.bottom !== null && line.y !== null ? line.y - previousLine.bottom : 0;\n\n    if (!lastParagraph || gap > paragraphGap) {\n      paragraphs.push({ lines: [line] });\n    } else {\n      lastParagraph.lines.push(line);\n    }\n  });\n\n  return paragraphs;\n};\n\nconst lineToText = (line) => line.words.map(({ word }) => word?.word || \"\").filter(Boolean).join(\" \`).replace(/`/g, '');\n\nconst paragraphsToPlainText = (paragraphs) => {\n  return paragraphs\n    .map((paragraph) => paragraph.lines.map(lineToText).filter(Boolean).join(\"\\n\"))\n    .filter(Boolean)\n    .join(\"\\n\\n\");\n};\n'''

# Fix accidental template quote in helper source before insertion
helpers = helpers.replace('join(" \`).replace(/`/g, \'\');', 'join(" ");')

if 'const getWordBox = (word)' not in review:
    review = review.replace('import API_BASE_URL from "../config";\n\n', 'import API_BASE_URL from "../config";\n' + helpers + '\n')

review = review.replace('  const imageRef = useRef(null);\n', '  const imageRef = useRef(null);\n  const originalPreviewRef = useRef(null);\n')

review = review.replace(
'''  const currentWords = pages[currentPage]?.text || [];\n  const remainingCount = pages.reduce((acc, page) => acc + (page.text || []).filter((word) => word.highlighted).length, 0);\n''',
'''  const currentWords = pages[currentPage]?.text || [];\n  const currentParagraphs = groupWordsIntoParagraphs(currentWords);\n  const remainingCount = pages.reduce((acc, page) => acc + (page.text || []).filter((word) => word.highlighted).length, 0);\n'''
)

old_highlight = '''  const updateOriginalHighlight = (wordData) => {\n    if (!imageRef.current || !wordData?.bounding_box) {\n      setHighlightedBox(null);\n      return;\n    }\n\n    const imageRect = imageRef.current.getBoundingClientRect();\n    const scaleX = imageRect.width / (wordData.bounding_box.original_width || 1);\n    const scaleY = imageRect.height / (wordData.bounding_box.original_height || 1);\n\n    setHighlightedBox({\n      x: wordData.bounding_box.x * scaleX,\n      y: wordData.bounding_box.y * scaleY,\n      w: wordData.bounding_box.w * scaleX,\n      h: wordData.bounding_box.h * scaleY,\n    });\n  };\n'''
new_highlight = '''  const updateOriginalHighlight = (wordData) => {\n    const box = getWordBox(wordData);\n    if (!imageRef.current || !originalPreviewRef.current || !box) {\n      setHighlightedBox(null);\n      return;\n    }\n\n    const image = imageRef.current;\n    if (!image.complete || image.naturalWidth === 0) {\n      setHighlightedBox(null);\n      return;\n    }\n\n    const imageRect = image.getBoundingClientRect();\n    const previewRect = originalPreviewRef.current.getBoundingClientRect();\n    const sourceWidth = getBoxMetric(box, \"original_width\", image.naturalWidth || imageRect.width || 1);\n    const sourceHeight = getBoxMetric(box, \"original_height\", image.naturalHeight || imageRect.height || 1);\n    const scaleX = imageRect.width / sourceWidth;\n    const scaleY = imageRect.height / sourceHeight;\n\n    setHighlightedBox({\n      x: (imageRect.left - previewRect.left) + originalPreviewRef.current.scrollLeft + (getBoxMetric(box, \"x\") * scaleX),\n      y: (imageRect.top - previewRect.top) + originalPreviewRef.current.scrollTop + (getBoxMetric(box, \"y\") * scaleY),\n      w: Math.max(10, getBoxMetric(box, \"w\") * scaleX),\n      h: Math.max(12, getBoxMetric(box, \"h\") * scaleY),\n    });\n  };\n'''
if old_highlight not in review:
    raise SystemExit('Highlight function block not found')
review = review.replace(old_highlight, new_highlight)

review = review.replace('      const response = await axios.post(`${API_BASE_URL}/suggest_correction`, {\n', '      const response = await axios.post(`${API_BASE_URL}/get_all_suggestions`, {\n')

review = review.replace(
'''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => (page.text || []).map((word) => word.word || \"\").join(\" \).trim())\n      .filter(Boolean)\n      .join(\"\\n\\n\");\n  };\n''',
'''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => paragraphsToPlainText(groupWordsIntoParagraphs(page.text || [])))\n      .filter(Boolean)\n      .join(\"\\n\\n\");\n  };\n'''
)
# The previous replace can fail because of quote escaping; do a simpler targeted replacement if needed.
if 'map((page) => (page.text || []).map((word) => word.word || "").join(" ").trim())' in review:
    review = review.replace(
'''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => (page.text || []).map((word) => word.word || \"\").join(\" \" ).trim())\n      .filter(Boolean)\n      .join(\"\\n\\n\");\n  };\n''',
'''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => paragraphsToPlainText(groupWordsIntoParagraphs(page.text || [])))\n      .filter(Boolean)\n      .join(\"\\n\\n\");\n  };\n'''
    )

# Robust replacement for exact block as currently in file.
old_plain = '''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => (page.text || []).map((word) => word.word || \"\").join(\" \ ").trim())\n      .filter(Boolean)\n      .join(\"\\n\\n\");\n  };\n'''
# no-op placeholder for unusual spacing

review = review.replace(
'''          <div className="original-preview">\n            <img\n              ref={imageRef}\n              src={`${API_BASE_URL}/uploads/original_page_${currentPage + 1}.png?t=${Date.now()}`}\n              alt="معاينة الصفحة الأصلية"\n              className="original-image"\n            />\n''',
'''          <div className="original-preview" ref={originalPreviewRef}>\n            <img\n              ref={imageRef}\n              src={`${API_BASE_URL}/uploads/original_page_${currentPage + 1}.png?t=${Date.now()}`}\n              alt="معاينة الصفحة الأصلية"\n              className="original-image"\n              onLoad={() => {\n                if (selectedWordInfo) updateOriginalHighlight(selectedWordInfo);\n              }}\n            />\n'''
)

old_render = '''          <div className="extracted-text" onClick={(event) => event.stopPropagation()}>\n            {currentWords.map((word, index) => {\n              const isSelected = selectedWordIndex === index && showSuggestions;\n              const className = [\n                "review-word",\n                word.highlighted ? "review-word--flagged" : "",\n                word.corrected ? "review-word--corrected" : "",\n                isSelected ? "review-word--selected" : "",\n              ].filter(Boolean).join(" ");\n\n              return (\n                <span\n                  key={index}\n                  className={className}\n                  onClick={(event) => handleWordClick(word, event, index)}\n                  title={word.highlighted ? "كلمة تحتاج مراجعة" : "اضغط للمراجعة"}\n                >\n                  {word.word}\n                </span>\n              );\n            })}\n          </div>\n'''
new_render = '''          <div className="extracted-text" onClick={(event) => event.stopPropagation()}>\n            {currentParagraphs.map((paragraph, paragraphIndex) => (\n              <p className="review-paragraph" key={`paragraph-${paragraphIndex}`}>\n                {paragraph.lines.map((line, lineIndex) => (\n                  <span className="review-line" key={`paragraph-${paragraphIndex}-line-${lineIndex}`}>\n                    {line.words.map(({ word, index }) => {\n                      const isSelected = selectedWordIndex === index && showSuggestions;\n                      const className = [\n                        "review-word",\n                        word.highlighted ? "review-word--flagged" : "",\n                        word.corrected ? "review-word--corrected" : "",\n                        isSelected ? "review-word--selected" : "",\n                      ].filter(Boolean).join(" ");\n\n                      return (\n                        <React.Fragment key={index}>\n                          <span\n                            className={className}\n                            onClick={(event) => handleWordClick(word, event, index)}\n                            title={word.highlighted ? "كلمة تحتاج مراجعة" : "اضغط للمراجعة"}\n                          >\n                            {word.word}\n                          </span>{" "}\n                        </React.Fragment>\n                      );\n                    })}\n                  </span>\n                ))}\n              </p>\n            ))}\n          </div>\n'''
if old_render not in review:
    raise SystemExit('Text render block not found')
review = review.replace(old_render, new_render)

# Ensure the plain-text export block is updated, because the earlier replacement intentionally leaves room for exact matching.
old_plain_exact = '''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => (page.text || []).map((word) => word.word || "").join(" ").trim())\n      .filter(Boolean)\n      .join("\\n\\n");\n  };\n'''
new_plain_exact = '''  const buildPlainTextFromPages = (pagesToExport = pages) => {\n    return pagesToExport\n      .map((page) => paragraphsToPlainText(groupWordsIntoParagraphs(page.text || [])))\n      .filter(Boolean)\n      .join("\\n\\n");\n  };\n'''
if old_plain_exact in review:
    review = review.replace(old_plain_exact, new_plain_exact)

review_path.write_text(review)

css = css_path.read_text()
if '.review-paragraph' not in css:
    css = css.replace(
'''  color: #1e293b;\n  font-size: 19px;\n  line-height: 2.35;\n}\n\n.review-word {\n  display: inline;\n''',
'''  color: #1e293b;\n  font-size: 19px;\n  line-height: 2.25;\n}\n\n.review-paragraph {\n  margin: 0 0 1.35rem;\n  padding: 0;\n  direction: rtl;\n  unicode-bidi: plaintext;\n}\n\n.review-paragraph:last-child { margin-bottom: 0; }\n\n.review-line {\n  display: block;\n  min-height: 1.85em;\n}\n\n.review-word {\n  display: inline-block;\n'''
    )

css_path.write_text(css)
print('Applied review UI fixes.')
