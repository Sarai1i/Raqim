import re

class RaqimPostProcessor:
    def __init__(self):
        # المعالج الآن يعمل دائماً برمجياً دون الحاجة لـ LLM
        pass
        
    def process_text(self, text):
        """
        المعالجة البرمجية للنص لتحسين التنسيق العام باستخدام القواعد (Regex).
        """
        if not text:
            return text
            
        # 1. تنظيف المسافات الزائدة (تحويل المسافات المتعددة لمسافة واحدة)
        text = re.sub(r' +', ' ', text)
        
        # 2. إصلاح علامات الترقيم العربية (إزالة المسافة قبل العلامة، وإضافتها بعدها)
        # تشمل: ، ؛ ؟ ! . :
        text = re.sub(r'\s+([،؛؟!\.:])', r'\1', text)
        text = re.sub(r'([،؛؟!\.:])(?=[^\s])', r'\1 ', text)
        
        # 3. إزالة السطور الفارغة المكررة (أكثر من سطرين)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 4. إصلاح الأقواس (إزالة المسافات الداخلية)
        text = re.sub(r'\(\s+', '(', text)
        text = re.sub(r'\s+\)', ')', text)
        
        # 5. تنظيف بداية ونهاية النص
        text = text.strip()
            
        return text

    def process_ocr_results(self, ocr_results):
        """
        معالجة نتائج OCR الكاملة برمجياً.
        """
        if not ocr_results:
            return ocr_results
            
        for page in ocr_results:
            if 'text' in page:
                for word_obj in page['text']:
                    if 'word' in word_obj:
                        # تنظيف كل كلمة بشكل فردي إذا لزم الأمر
                        word_obj['word'] = word_obj['word'].strip()
            
        return ocr_results

post_processor = RaqimPostProcessor()
