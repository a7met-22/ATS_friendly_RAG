


import asyncio
import time
from parsingWays.llama_parsing import parse_single_pdf, parse_pdf_directory

async def run_test():
    print("🚀 بدء اختبار الـ Async Parser...")
    start_time = time.perf_counter()

    sample_pdf = "./uploaded_pdfs/2cafb146063dc99b0a1b5b9fbf414ef7f3bfc1622b8155a9db3fc0be47dec133_04_Software_Engineering_Sara_Adel.pdf"
 
    
    try:
        result = await parse_single_pdf(sample_pdf)
        elapsed = time.perf_counter() - start_time
        
        print(f"✅ تم بنجاح في {elapsed:.2f} ثانية!")
        print(f"📄 اسم الملف: {result['file_name']}")
        print(f"📑 عدد الصفحات المستخرجة: {len(result['pages'])}")
        print(f"📝 أول 200 حرف:\n{result['text'][:200]}...")
        
    except Exception as e:
        print(f"❌ حصل خطأ أثناء الاختبار:\n{type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
