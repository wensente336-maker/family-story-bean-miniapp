from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class HighlightRepository(Protocol):
    def save_from_moment(self, user_id: UUID, moment_id: UUID, share_allowed: bool = True) -> dict | None: ...
    def list_for_user(self, user_id: UUID, trashed: bool = False) -> list[dict]: ...
    def get_for_user(self, user_id: UUID, work_id: UUID, trashed: bool = False) -> dict | None: ...
    def update(self, user_id: UUID, work_id: UUID, title: str, quote: str) -> dict | None: ...
    def set_audio(self, work_id: UUID, status: str, key: str | None = None, code: str | None = None) -> None: ...
    def save_cover(self, user_id: UUID, work_id: UUID, cover: dict) -> tuple[dict,list[str]] | None: ...
    def delete_cover(self, user_id: UUID, work_id: UUID) -> list[str] | None: ...
    def set_deleted(self, user_id: UUID, work_id: UUID, deleted: bool) -> dict | None: ...
    def create_share(self, user_id: UUID, work_id: UUID, hours: int) -> dict | None: ...
    def list_shares(self, user_id: UUID, work_id: UUID) -> list[dict]: ...
    def revoke_share(self, user_id: UUID, share_id: UUID) -> dict | None: ...
    def resolve_share(self, token: str, count_access: bool = True) -> dict | None: ...
    def set_like(self, user_id: UUID, work_id: UUID, liked: bool) -> dict | None: ...
    def list_comments(self, user_id: UUID, work_id: UUID, cursor: UUID | None, limit: int) -> dict | None: ...
    def create_comment(self, user_id: UUID, work_id: UUID, body: str) -> dict | None: ...
    def update_comment(self, user_id: UUID, comment_id: UUID, body: str) -> dict | None: ...
    def delete_comment(self, user_id: UUID, comment_id: UUID) -> dict | None: ...


class PostgresHighlightRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url.replace('postgresql+psycopg://','postgresql://',1)

    def _connect(self):
        return psycopg.connect(self.database_url,row_factory=dict_row)

    @staticmethod
    def _payload(connection, row: dict, user_id: UUID | None = None) -> dict:
        cover = connection.execute('SELECT * FROM highlight_cover_assets WHERE highlight_work_id=%s',(row['id'],)).fetchone()
        recording = connection.execute('SELECT object_key FROM recordings WHERE id=%s',(row['recording_id'],)).fetchone()
        members = connection.execute(
            """SELECT DISTINCT segment.family_member_id FROM transcript_segments segment
            WHERE segment.recording_id=%s AND segment.start_ms<%s AND segment.end_ms>%s
              AND segment.family_member_id IS NOT NULL""",(row['recording_id'],row['end_ms'],row['start_ms'])
        ).fetchall()
        interaction = connection.execute(
            """SELECT
              (SELECT count(*) FROM highlight_reactions WHERE highlight_work_id=%s AND reaction_type='LIKE') AS like_count,
              (SELECT count(*) FROM highlight_comments WHERE highlight_work_id=%s AND status='ACTIVE') AS comment_count,
              EXISTS(SELECT 1 FROM highlight_reactions WHERE highlight_work_id=%s AND user_id=%s AND reaction_type='LIKE') AS liked_by_me""",
            (row['id'],row['id'],row['id'],user_id),
        ).fetchone() if user_id else {'like_count':0,'comment_count':0,'liked_by_me':False}
        return {**row,'duration_ms':row['end_ms']-row['start_ms'],'cover':cover,
                'source_object_key':recording['object_key'] if recording else None,
                'member_ids':[item['family_member_id'] for item in members],
                **interaction,'can_edit':True,'can_comment':row.get('deleted_at') is None}

    def save_from_moment(self,user_id,moment_id,share_allowed=True):
        with self._connect() as connection:
            moment=connection.execute(
                """SELECT moment.*,recording.object_key AS source_object_key
                FROM moments moment JOIN recordings recording ON recording.id=moment.recording_id
                JOIN families family ON family.id=moment.family_id
                WHERE moment.id=%s AND family.owner_user_id=%s AND moment.selection_state='kept'
                  AND moment.start_ms IS NOT NULL AND moment.end_ms IS NOT NULL""",(moment_id,user_id)
            ).fetchone()
            if not moment:return None
            quote=str((moment['storyboard'] or {}).get('highlight_quote') or moment['title']).strip()
            row=connection.execute(
                """INSERT INTO highlight_works
                (family_id,source_moment_id,recording_id,created_by_user_id,title,quote,share_allowed,start_ms,end_ms)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(source_moment_id) DO UPDATE SET deleted_at=NULL,deleted_by_user_id=NULL,
                  share_allowed=EXCLUDED.share_allowed
                RETURNING *""",(moment['family_id'],moment_id,moment['recording_id'],user_id,moment['title'],quote,share_allowed,moment['start_ms'],moment['end_ms'])
            ).fetchone()
            return {**self._payload(connection,row,user_id),'source_object_key':moment['source_object_key']}

    def list_for_user(self,user_id,trashed=False):
        with self._connect() as connection:
            rows=connection.execute(
                """SELECT work.* FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE family.owner_user_id=%s AND (work.deleted_at IS NOT NULL)=%s
                ORDER BY COALESCE(work.deleted_at,work.created_at) DESC""",(user_id,trashed)
            ).fetchall()
            return [self._payload(connection,row,user_id) for row in rows]

    def get_for_user(self,user_id,work_id,trashed=False):
        with self._connect() as connection:
            row=connection.execute(
                """SELECT work.* FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND (work.deleted_at IS NOT NULL)=%s""",(work_id,user_id,trashed)
            ).fetchone()
            return self._payload(connection,row,user_id) if row else None

    def update(self,user_id,work_id,title,quote):
        with self._connect() as connection:
            row=connection.execute(
                """UPDATE highlight_works work SET title=%s,quote=%s,updated_at=now()
                FROM families family WHERE work.id=%s AND family.id=work.family_id
                  AND family.owner_user_id=%s AND work.deleted_at IS NULL RETURNING work.*""",
                (title.strip(),quote.strip(),work_id,user_id)).fetchone()
            return self._payload(connection,row,user_id) if row else None

    def set_audio(self,work_id,status,key=None,code=None):
        with self._connect() as connection:
            connection.execute("UPDATE highlight_works SET audio_status=%s,audio_object_key=%s,audio_failure_code=%s,updated_at=now() WHERE id=%s",
                               (status,key,code,work_id))

    def save_cover(self,user_id,work_id,cover):
        with self._connect() as connection:
            work=connection.execute("""SELECT work.* FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL FOR UPDATE OF work""",(work_id,user_id)).fetchone()
            if not work:return None
            old=connection.execute('SELECT object_key,thumbnail_object_key FROM highlight_cover_assets WHERE highlight_work_id=%s',(work_id,)).fetchone()
            connection.execute("""INSERT INTO highlight_cover_assets
                (family_id,highlight_work_id,object_key,thumbnail_object_key,width,height,byte_size,sha256,
                 aspect_ratio,layout_version,focal_x,focal_y)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(highlight_work_id) DO UPDATE SET object_key=EXCLUDED.object_key,
                thumbnail_object_key=EXCLUDED.thumbnail_object_key,width=EXCLUDED.width,height=EXCLUDED.height,
                byte_size=EXCLUDED.byte_size,sha256=EXCLUDED.sha256,aspect_ratio=EXCLUDED.aspect_ratio,
                layout_version=EXCLUDED.layout_version,focal_x=EXCLUDED.focal_x,focal_y=EXCLUDED.focal_y,
                updated_at=now()""",
                (work['family_id'],work_id,cover['object_key'],cover['thumbnail_object_key'],cover['width'],cover['height'],cover['byte_size'],cover['sha256'],cover['aspect_ratio'],cover['layout_version'],cover['focal_x'],cover['focal_y']))
            fresh=connection.execute('SELECT * FROM highlight_works WHERE id=%s',(work_id,)).fetchone()
            return self._payload(connection,fresh,user_id),[value for value in (old or {}).values() if value]

    def delete_cover(self,user_id,work_id):
        with self._connect() as connection:
            work=connection.execute("""SELECT work.id FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL""",(work_id,user_id)).fetchone()
            if not work:return None
            old=connection.execute('DELETE FROM highlight_cover_assets WHERE highlight_work_id=%s RETURNING object_key,thumbnail_object_key',(work_id,)).fetchone()
            return [value for value in (old or {}).values() if value]

    def set_deleted(self,user_id,work_id,deleted):
        with self._connect() as connection:
            work=connection.execute("""SELECT work.* FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s FOR UPDATE OF work""",(work_id,user_id)).fetchone()
            if not work:return None
            if bool(work['deleted_at'])==deleted:return {'id':work_id,'deleted_at':work['deleted_at']}
            row=connection.execute("""UPDATE highlight_works SET deleted_at=CASE WHEN %s THEN now() ELSE NULL END,
                deleted_by_user_id=CASE WHEN %s THEN %s::uuid ELSE NULL END WHERE id=%s RETURNING deleted_at""",
                (deleted,deleted,user_id,work_id)).fetchone()
            if deleted:connection.execute('UPDATE highlight_shares SET revoked_at=COALESCE(revoked_at,now()) WHERE highlight_work_id=%s',(work_id,))
            connection.execute("""INSERT INTO deletion_audits(family_id,requested_by_user_id,scope,target_id,result,completed_at)
                VALUES (%s,%s,%s,%s,'COMPLETED',now())""",(work['family_id'],user_id,'highlight_trash' if deleted else 'highlight_restore',work_id))
            return {'id':work_id,'deleted_at':row['deleted_at']}

    def create_share(self,user_id,work_id,hours):
        token=secrets.token_urlsafe(32)
        with self._connect() as connection:
            work=connection.execute("""SELECT work.* FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL
                  AND work.audio_status='READY' AND work.share_allowed=true
                FOR UPDATE OF work""",(work_id,user_id)).fetchone()
            if not work:return None
            privacy=connection.execute("""INSERT INTO family_privacy_settings(family_id) VALUES(%s)
                ON CONFLICT(family_id) DO UPDATE SET family_id=EXCLUDED.family_id RETURNING sharing_enabled""",(work['family_id'],)).fetchone()
            if not privacy['sharing_enabled']:return None
            share=connection.execute("""INSERT INTO highlight_shares
                (family_id,highlight_work_id,created_by_user_id,token_hash,expires_at)
                VALUES(%s,%s,%s,%s,%s) RETURNING *""",
                (work['family_id'],work_id,user_id,token_hash(token),datetime.now(UTC)+timedelta(hours=hours))).fetchone()
            return {**share,'title':work['title'],'token':token}

    def list_shares(self,user_id,work_id):
        with self._connect() as connection:return connection.execute("""SELECT share.*,work.title FROM highlight_shares share
            JOIN highlight_works work ON work.id=share.highlight_work_id JOIN families family ON family.id=share.family_id
            WHERE share.highlight_work_id=%s AND family.owner_user_id=%s ORDER BY share.created_at DESC""",(work_id,user_id)).fetchall()

    def revoke_share(self,user_id,share_id):
        with self._connect() as connection:return connection.execute("""UPDATE highlight_shares share SET revoked_at=COALESCE(revoked_at,now())
            FROM highlight_works work,families family WHERE share.id=%s AND work.id=share.highlight_work_id
              AND family.id=share.family_id AND family.owner_user_id=%s RETURNING share.*,work.title""",(share_id,user_id)).fetchone()

    def set_like(self,user_id,work_id,liked):
        with self._connect() as connection:
            work=connection.execute("""SELECT work.family_id FROM highlight_works work
                JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL""",(work_id,user_id)).fetchone()
            if not work:return None
            if liked:
                connection.execute("""INSERT INTO highlight_reactions(family_id,highlight_work_id,user_id)
                    VALUES(%s,%s,%s) ON CONFLICT(highlight_work_id,user_id,reaction_type) DO NOTHING""",
                    (work['family_id'],work_id,user_id))
            else:
                connection.execute("DELETE FROM highlight_reactions WHERE highlight_work_id=%s AND user_id=%s AND reaction_type='LIKE'",(work_id,user_id))
            count=connection.execute("SELECT count(*) AS value FROM highlight_reactions WHERE highlight_work_id=%s AND reaction_type='LIKE'",(work_id,)).fetchone()['value']
            return {'highlight_work_id':work_id,'liked':liked,'like_count':count}

    @staticmethod
    def _comment_payload(row,user_id):
        return {**row,'can_edit':row.get('author_user_id')==user_id,'can_delete':True}

    def list_comments(self,user_id,work_id,cursor,limit):
        with self._connect() as connection:
            owned=connection.execute("""SELECT 1 FROM highlight_works work JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL""",(work_id,user_id)).fetchone()
            if not owned:return None
            rows=connection.execute("""SELECT comment.* FROM highlight_comments comment
                WHERE comment.highlight_work_id=%s AND comment.status='ACTIVE'
                  AND (%s::uuid IS NULL OR (comment.created_at,comment.id) <
                    (SELECT created_at,id FROM highlight_comments WHERE id=%s AND highlight_work_id=%s))
                ORDER BY comment.created_at DESC,comment.id DESC LIMIT %s""",
                (work_id,cursor,cursor,work_id,limit+1)).fetchall()
            has_more=len(rows)>limit;rows=rows[:limit]
            return {'items':[self._comment_payload(row,user_id) for row in rows],
                    'next_cursor':rows[-1]['id'] if has_more and rows else None}

    def create_comment(self,user_id,work_id,body):
        with self._connect() as connection:
            work=connection.execute("""SELECT work.family_id FROM highlight_works work
                JOIN families family ON family.id=work.family_id
                WHERE work.id=%s AND family.owner_user_id=%s AND work.deleted_at IS NULL""",(work_id,user_id)).fetchone()
            if not work:return None
            author=connection.execute("SELECT nickname FROM family_members WHERE family_id=%s ORDER BY created_at,id LIMIT 1",(work['family_id'],)).fetchone()
            row=connection.execute("""INSERT INTO highlight_comments
                (family_id,highlight_work_id,author_user_id,author_name,body)
                VALUES(%s,%s,%s,%s,%s) RETURNING *""",
                (work['family_id'],work_id,user_id,author['nickname'] if author else '家庭成员',body.strip())).fetchone()
            return self._comment_payload(row,user_id)

    def update_comment(self,user_id,comment_id,body):
        with self._connect() as connection:
            row=connection.execute("""UPDATE highlight_comments comment SET body=%s,updated_at=now()
                FROM highlight_works work,families family
                WHERE comment.id=%s AND comment.author_user_id=%s AND comment.status='ACTIVE'
                  AND work.id=comment.highlight_work_id AND work.deleted_at IS NULL
                  AND family.id=comment.family_id AND family.owner_user_id=%s
                RETURNING comment.*""",(body.strip(),comment_id,user_id,user_id)).fetchone()
            return self._comment_payload(row,user_id) if row else None

    def delete_comment(self,user_id,comment_id):
        with self._connect() as connection:
            row=connection.execute("""UPDATE highlight_comments comment
                SET status='DELETED',deleted_at=now(),updated_at=now()
                FROM highlight_works work,families family
                WHERE comment.id=%s AND comment.status='ACTIVE' AND work.id=comment.highlight_work_id
                  AND family.id=comment.family_id AND family.owner_user_id=%s
                RETURNING comment.id,comment.highlight_work_id""",(comment_id,user_id)).fetchone()
            return row

    def resolve_share(self,token,count_access=True):
        with self._connect() as connection:
            row=connection.execute("""SELECT share.*,work.title,work.quote,work.recording_id,work.audio_object_key,
                work.start_ms,work.end_ms,cover.object_key AS cover_object_key
                FROM highlight_shares share JOIN highlight_works work ON work.id=share.highlight_work_id
                LEFT JOIN highlight_cover_assets cover ON cover.highlight_work_id=work.id
                WHERE share.token_hash=%s AND share.revoked_at IS NULL AND share.expires_at>now()
                  AND work.deleted_at IS NULL AND work.audio_status='READY'""",(token_hash(token),)).fetchone()
            if not row:return None
            if count_access:connection.execute('UPDATE highlight_shares SET access_count=access_count+1,last_accessed_at=now() WHERE id=%s',(row['id'],))
            return {**row,'duration_ms':row['end_ms']-row['start_ms']}
