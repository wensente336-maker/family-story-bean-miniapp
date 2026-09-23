from uuid import UUID

from .contracts import (
    FamilySummary,
    HomeData,
    JobData,
    JobStage,
    MomentSummary,
    ProcessingSummary,
)


FAMILY_ID = UUID("11111111-1111-4111-8111-111111111111")
RECORDING_ID = UUID("22222222-2222-4222-8222-222222222222")
JOB_ID = UUID("33333333-3333-4333-8333-333333333333")


def build_home_data() -> HomeData:
    return HomeData(
        family=FamilySummary(
            id=FAMILY_ID,
            name="小满一家",
            member_labels=["爸", "妈", "满"],
        ),
        processing=ProcessingSummary(
            recording_id=RECORDING_ID,
            job_id=JOB_ID,
            title="周日晚餐",
            detail="正在发现值得留下的时刻",
            stage=JobStage.analyzing,
            progress=68,
        ),
        moments=[
            MomentSummary(
                id=UUID("44444444-4444-4444-8444-444444444441"),
                recording_id=RECORDING_ID,
                theme="童言童语",
                duration_ms=48_000,
                title="月亮是天空的夜灯",
                quote="那星星就是忘记关掉的小灯吗？",
                color="sun",
            ),
            MomentSummary(
                id=UUID("44444444-4444-4444-8444-444444444442"),
                recording_id=RECORDING_ID,
                theme="家庭趣事",
                duration_ms=72_000,
                title="爸爸的海水蛋糕",
                quote="爸爸，你是不是把盐当成糖啦？",
                color="coral",
            ),
        ],
    )


def build_job_data() -> JobData:
    return JobData(
        id=JOB_ID,
        recording_id=RECORDING_ID,
        stage=JobStage.analyzing,
        progress=68,
        retry_count=0,
        pipeline_version="storyboard-v1",
    )
