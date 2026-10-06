use async_trait::async_trait;
use hbb_common::{log, ResultType};
use sqlx::{
    sqlite::SqliteConnectOptions, ConnectOptions, Connection, Error as SqlxError, SqliteConnection,
};
use std::{ops::DerefMut, str::FromStr};
//use sqlx::postgres::PgPoolOptions;
//use sqlx::mysql::MySqlPoolOptions;

type Pool = deadpool::managed::Pool<DbPool>;

pub struct DbPool {
    url: String,
}

#[async_trait]
impl deadpool::managed::Manager for DbPool {
    type Type = SqliteConnection;
    type Error = SqlxError;
    async fn create(&self) -> Result<SqliteConnection, SqlxError> {
        let opt =
            SqliteConnectOptions::from_str(&self.url)?.log_statements(log::LevelFilter::Debug);
        SqliteConnection::connect_with(&opt).await
    }
    async fn recycle(
        &self,
        obj: &mut SqliteConnection,
    ) -> deadpool::managed::RecycleResult<SqlxError> {
        Ok(obj.ping().await?)
    }
}

#[derive(Clone)]
pub struct Database {
    pool: Pool,
}

#[derive(Default)]
pub struct Peer {
    pub guid: Vec<u8>,
    pub uuid: Vec<u8>,
    pub pk: Vec<u8>,
    pub info: String,
}

impl Database {
    pub async fn new(url: &str) -> ResultType<Database> {
        if !std::path::Path::new(url).exists() {
            std::fs::File::create(url).ok();
        }
        let n: usize = std::env::var("MAX_DATABASE_CONNECTIONS")
            .unwrap_or_else(|_| "1".to_owned())
            .parse()
            .unwrap_or(1);
        log::debug!("MAX_DATABASE_CONNECTIONS={}", n);
        let pool = Pool::new(
            DbPool {
                url: url.to_owned(),
            },
            n,
        );
        let _ = pool.get().await?; // test
        let db = Database { pool };
        db.create_tables().await?;
        Ok(db)
    }

    async fn create_tables(&self) -> ResultType<()> {
        sqlx::raw_sql(
            "
            create table if not exists peer (
                guid blob primary key not null,
                id varchar(100) not null,
                uuid blob not null,
                pk blob not null,
                created_at datetime not null default(current_timestamp),
                user blob,
                status tinyint,
                note varchar(300),
                info text not null
            ) without rowid;
            create unique index if not exists index_peer_id on peer (id);
            create index if not exists index_peer_user on peer (user);
            create index if not exists index_peer_created_at on peer (created_at);
            create index if not exists index_peer_status on peer (status);
        ",
        )
        .execute(self.pool.get().await?.deref_mut())
        .await?;
        Ok(())
    }

    pub async fn get_peer(&self, id: &str) -> ResultType<Option<Peer>> {
        let row = sqlx::query_as::<_, (Vec<u8>, Vec<u8>, Vec<u8>, String)>(
            "select guid, uuid, pk, info from peer where id = ?",
        )
        .bind(id)
        .fetch_optional(self.pool.get().await?.deref_mut())
        .await?;
        Ok(row.map(|(guid, uuid, pk, info)| Peer {
            guid,
            uuid,
            pk,
            info,
        }))
    }

    pub async fn insert_peer(
        &self,
        id: &str,
        uuid: &[u8],
        pk: &[u8],
        info: &str,
    ) -> ResultType<Vec<u8>> {
        let guid = uuid::Uuid::new_v4().as_bytes().to_vec();
        sqlx::query("insert into peer(guid, id, uuid, pk, info) values(?, ?, ?, ?, ?)")
            .bind(&guid)
            .bind(id)
            .bind(uuid)
            .bind(pk)
            .bind(info)
            .execute(self.pool.get().await?.deref_mut())
            .await?;
        Ok(guid)
    }

    pub async fn update_pk(
        &self,
        guid: &Vec<u8>,
        id: &str,
        pk: &[u8],
        info: &str,
    ) -> ResultType<()> {
        sqlx::query("update peer set id=?, pk=?, info=? where guid=?")
            .bind(id)
            .bind(pk)
            .bind(info)
            .bind(guid)
            .execute(self.pool.get().await?.deref_mut())
            .await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use hbb_common::tokio;

    #[tokio::test]
    async fn sqlite_peer_round_trip() {
        let path =
            std::env::temp_dir().join(format!("rustdesk-peer-{}.sqlite3", uuid::Uuid::new_v4()));
        let db = super::Database::new(path.to_str().unwrap()).await.unwrap();
        assert!(db.get_peer("missing").await.unwrap().is_none());
        let guid = db
            .insert_peer("peer-a", b"uuid", b"key", "original")
            .await
            .unwrap();
        let peer = db.get_peer("peer-a").await.unwrap().unwrap();
        assert_eq!(peer.guid, guid);
        assert_eq!(peer.uuid, b"uuid");
        assert_eq!(peer.pk, b"key");
        assert_eq!(peer.info, "original");
        assert!(db
            .insert_peer("peer-a", b"other", b"other", "duplicate")
            .await
            .is_err());
        db.update_pk(&guid, "peer-b", b"new-key", "updated")
            .await
            .unwrap();
        assert!(db.get_peer("peer-a").await.unwrap().is_none());
        let peer = db.get_peer("peer-b").await.unwrap().unwrap();
        assert_eq!(peer.guid, guid);
        assert_eq!(peer.uuid, b"uuid");
        assert_eq!(peer.pk, b"new-key");
        assert_eq!(peer.info, "updated");
        drop(db);
        std::fs::remove_file(path).unwrap();
    }

    #[tokio::test]
    async fn invalid_sqlite_options_return_an_error() {
        use deadpool::managed::Manager;
        let manager = super::DbPool {
            url: "sqlite://unused.db?mode=invalid".to_owned(),
        };
        assert!(manager.create().await.is_err());
    }

    #[test]
    fn test_insert() {
        insert();
    }

    #[tokio::main(flavor = "multi_thread")]
    async fn insert() {
        let path =
            std::env::temp_dir().join(format!("rustdesk-stress-{}.sqlite3", uuid::Uuid::new_v4()));
        let db = super::Database::new(path.to_str().unwrap()).await.unwrap();
        let mut jobs = vec![];
        for i in 0..10000 {
            let cloned = db.clone();
            let id = i.to_string();
            let a = tokio::spawn(async move {
                let empty_vec = Vec::new();
                cloned
                    .insert_peer(&id, &empty_vec, &empty_vec, "")
                    .await
                    .unwrap();
            });
            jobs.push(a);
        }
        for i in 0..10000 {
            let cloned = db.clone();
            let id = i.to_string();
            let a = tokio::spawn(async move {
                cloned.get_peer(&id).await.unwrap();
            });
            jobs.push(a);
        }
        for job in hbb_common::futures::future::join_all(jobs).await {
            job.unwrap();
        }
        assert!(db.get_peer("9999").await.unwrap().is_some());
        drop(db);
        std::fs::remove_file(path).unwrap();
    }
}
