

import asyncio
import psycopg 
from database_utilities.database_connection import get_connection
from database_utilities.document_utilities import (
    delete_document,
    document_has_complete_embeddings,
    get_document,
    insert_document,
    set_document_status,
    update_document,
)


async def run_db_test():
    print("🚀 بدء اختبار دوال الداتابيز (Async Database Utilities)...")
    conn = await get_connection()

    # بيانات وهمية للتجربة
    dummy_file = {
        "id": "test_drive_id_999999",
        "name": "test_async_resume.pdf",
        "mimeType": "application/pdf",
        "appProperties": {"specialization": "AI Engineer"},
    }

    try:
        # بنستخدم try/finally مع rollback عشان نمسح بيانات الاختبار أوتوماتيك في الآخر
        async with conn.transaction():
            # 1. اختبار الإضافة (Insert)
            doc_id = await insert_document(
                conn=conn,
                file=dummy_file,
                content_hash="hash_v1_abc123",
                folder_id="test_folder_123",
                status="pending",
            )
            print(f"✅ 1. Insert نجح! (Document ID: {doc_id})")

            # 2. اختبار القراءة (Get)
            doc = await get_document(conn, dummy_file["id"])
            assert doc is not None and doc[0] == doc_id
            print(f"✅ 2. Get نجح! البيانات: {doc}")

            # 3. اختبار تغيير الحالة (Set Status)
            await set_document_status(conn, doc_id, "processing")
            print("✅ 3. Set Status نجح!")

            # 4. اختبار التحديث (Update)
            updated_id, new_ver = await update_document(
                conn=conn,
                document=doc,
                file=dummy_file,
                content_hash="hash_v2_xyz789",
                status="processed",
            )
            assert new_ver == 2
            print(f"✅ 4. Update نجح! الإصدار الجديد: {new_ver}")

            # 5. اختبار فحص الـ Embeddings
            has_emb = await document_has_complete_embeddings(conn, doc_id)
            assert has_emb is False  # لسه مضفناش chunks
            print(f"✅ 5. Check Embeddings نجح! النتيجة: {has_emb}")

            # 6. اختبار الحذف (Delete)
            deleted_name = await delete_document(conn, dummy_file["id"])
            assert deleted_name == dummy_file["name"]
            print(f"✅ 6. Delete نجح! تم حذف: {deleted_name}")

            # تراجع عن كل حاجة عشان الداتابيز تفضل نضيفة
            raise psycopg.Rollback()
            print("🧹 تم عمل Rollback بنجاح (الداتابيز نضيفة تماماً).")

    except Exception as e:
        print(f"❌ حصل خطأ أثناء اختبار الداتابيز:\n{type(e).__name__}: {e}")
    finally:
        await conn.close()
        print("🔌 تم إغلاق الاتصال بالداتابيز.")


if __name__ == "__main__":
    asyncio.run(run_db_test())
