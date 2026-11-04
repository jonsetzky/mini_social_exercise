# Mini Social

This is a mock social media platform created for the Social Computing course at the University of Oulu by Dr. Aku Visuri and Daniel Szabo.

The codebase contains three missing implementations, which you find [at end of app.py](https://github.com/Crowd-Computing-Oulu/mini_social_exercise/blob/44117e36e609b52c3452226797a0fd3fb5ff5258/app.py#L886). These are part of the coding assignments #1 and #2.

The repository contains a ready database, you do not have to create your own data.

## Usage (for students)

1. Create a [fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) of this repository
2. Clone your forked repository onto your computer
3. Make sure you have [uv](https://docs.astral.sh/uv/) installed
4. Start the server by running `uv run app.py`
5. The web application will be available at http://127.0.0.1:8080. 
6. The admin interface is at http://127.0.0.1:8080/admin, available only to the Admin user (username: admin, pw: admin)
7. Make sure your fork is public, and add its URL to your coursework assignments.

### Docker

If you prefer to run Mini-Social as a docker container, you can build the image and run it as follows:

1. Build image with `docker build --tag mini-social .`
2. Run image with the following command, where 8000 is the port you will access the application at `http://127.0.0.1:8000`

```
docker run -d -p 8000:5000 \
    --restart always \
    -v $(pwd)/database.sqlite:/python-docker/database.sqlite \
    mini-social
```
 

## Communities migration

Before starting the updated application, back up `database.sqlite`, then run `python migrate_communities.py database.sqlite` from the project directory. The migration preserves existing posts and assigns them to `general`; it can be run again safely.

Run the migration again after updating to add existing users to `general` once. New accounts join `general` automatically; users can leave it. Subsequent migration runs do not rejoin users who have left.

After updating, run the communities migration again to add the community description field.

Rerun the communities migration after updating to remove any existing wilderness memberships.

After updating, rerun the communities migration to add clan tags and backfill achievements from existing activity.

Rerun the communities migration to ensure that `/c/wilderness` exists for redirected posts.

Rerun the migration after updating to create `/c/introduction` and add existing newcomers once. New accounts automatically join both `general` and `introduction`. A newcomer has an account younger than seven days and has not posted in `introduction`. The homepage invites them to introduce themselves and selects that community by default. Visitors see a kindness reminder when entering introduction, and replies to newcomers require confirmation before publishing (design claims 18, 19 and 21). `/c/introducton` redirects to the canonical spelling.

The homepage always keeps the basic post form. Optional guiding questions appear only inside `/c/introduction`. Only accounts younger than seven days that have never published an introduction may publish there; other users can still browse and welcome newcomers in comments. Deleting an introduction does not restore posting eligibility. The homepage invitation opens the form without the entry reminder; ordinary introduction visits still show it. Nicknames are disabled in introduction. Rerun the migration to backfill introduction history and clear existing introduction nicknames; other community nicknames are preserved.

Rerun the migration to add `communities.show_in_main_feed`. Introduction and wilderness default to `0`; other communities default to `1`. All homepage sorts and Following respect this field, while community pages and direct post links remain available. Change this setting directly in the database; it is not exposed through the user interface. Repeated migrations preserve configured values.
