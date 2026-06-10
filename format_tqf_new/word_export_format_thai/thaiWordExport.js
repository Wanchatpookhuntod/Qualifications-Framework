"use strict";

const THAI_RE = /[\u0E00-\u0E7F]/;
const ZWSP = "\u200B";

function normalizeNewlines(value) {
  return String(value ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function segmentThaiWords(text, locale = "th") {
  const input = String(text ?? "");

  if (!THAI_RE.test(input)) {
    return input;
  }

  if (typeof Intl === "undefined" || typeof Intl.Segmenter === "undefined") {
    return input;
  }

  const segmenter = new Intl.Segmenter(locale, { granularity: "word" });
  const output = [];

  for (const part of segmenter.segment(input)) {
    output.push(part.segment);
    if (part.isWordLike && THAI_RE.test(part.segment)) {
      output.push(ZWSP);
    }
  }

  return output.join("").replace(/\u200B(?=\s|$)/g, "");
}

function escapeXml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function prepareThaiTextForWord(value) {
  return segmentThaiWords(normalizeNewlines(value));
}

function splitWordParagraphs(value) {
  return prepareThaiTextForWord(value)
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.split("\n"));
}

function wordRunXml(text, runPropertiesXml = "") {
  return [
    "<w:r>",
    runPropertiesXml,
    `<w:t xml:space="preserve">${escapeXml(text)}</w:t>`,
    "</w:r>",
  ].join("");
}

function wordParagraphXml(value, paragraphPropertiesXml = "", runPropertiesXml = defaultThaiRunPropertiesXml()) {
  const lines = prepareThaiTextForWord(value).split("\n");
  const body = lines
    .map((line, index) => {
      const prefix = index === 0 ? "" : "<w:br/>";
      return `${prefix}<w:t xml:space="preserve">${escapeXml(line)}</w:t>`;
    })
    .join("");

  return `<w:p>${paragraphPropertiesXml}<w:r>${runPropertiesXml}${body}</w:r></w:p>`;
}

function defaultThaiRunPropertiesXml() {
  return [
    "<w:rPr>",
    '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Arial Unicode MS" w:cs="Arial Unicode MS"/>',
    '<w:lang w:val="th-TH" w:eastAsia="th-TH" w:bidi="th-TH"/>',
    '<w:sz w:val="24"/>',
    '<w:szCs w:val="24"/>',
    "</w:rPr>",
  ].join("");
}

module.exports = {
  ZWSP,
  normalizeNewlines,
  segmentThaiWords,
  prepareThaiTextForWord,
  splitWordParagraphs,
  escapeXml,
  wordRunXml,
  wordParagraphXml,
  defaultThaiRunPropertiesXml,
};
