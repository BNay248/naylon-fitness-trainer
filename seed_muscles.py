"""Seeds the muscle_groups and muscles collections with the standard gym-level list.

    python seed_muscles.py [mongodb-uri]            # adds whatever is missing (matched by name)
    python seed_muscles.py [mongodb-uri] --reset    # wipes both collections and every exercise's muscle fields first

Muscles are named the way lifters refer to them; the description carries the anatomical name and
what the muscle does, following the ExRx.net muscle directory and standard anatomy references.
"""
import sys

from db_manager import ADDED_GROUP_FIELDS, GROUP_FIELDS, MUSCLE_FIELDS, TrainerDB

GROUPS = {
    "Chest": ("Muscles on the front of the ribcage that push the arms forward and across the body.", [
        ("Upper Chest", "Pectoralis major, clavicular head. Flexes the shoulder and brings the arm across the body; emphasised by incline pressing and low-to-high flyes."),
        ("Mid Chest", "Pectoralis major, sternal head. The bulk of the chest; drives horizontal pressing and flyes."),
        ("Lower Chest", "Pectoralis major, lower sternal and abdominal fibres. Pulls the arm down and across; emphasised by dips and decline pressing."),
        ("Pectoralis Minor", "Small muscle under the pec major. Pulls the shoulder blade forward and down; works in dips and push-ups."),
        ("Serratus Anterior", "Fans along the side of the ribs. Pulls the shoulder blade forward and rotates it up; works in punching, push-up plus and overhead reaching."),
    ]),
    "Back": ("Muscles of the upper and lower back that pull, retract the shoulder blades and extend the spine.", [
        ("Lats", "Latissimus dorsi. The broadest back muscle; pulls the arm down and back in pull-ups, pulldowns and rows."),
        ("Teres Major", "Sits just above the lats and does the same job (\"lat's little helper\"); works in pull-ups and rows."),
        ("Upper Traps", "Trapezius, upper fibres. Elevates the shoulder blades and supports the neck; shrugs, carries and deadlifts."),
        ("Middle Traps", "Trapezius, middle fibres. Squeezes the shoulder blades together; rows, face pulls and reverse flyes."),
        ("Lower Traps", "Trapezius, lower fibres. Pulls the shoulder blades down and rotates them up; Y-raises and overhead stability."),
        ("Rhomboids", "Rhomboid major and minor, between the shoulder blades. Retracts the shoulder blades; rows and band pull-aparts."),
        ("Erector Spinae", "The spinal erectors (iliocostalis, longissimus, spinalis); the \"lower back\". Extends and stabilises the spine in deadlifts, good mornings and back extensions."),
    ]),
    "Shoulders": ("The deltoids and rotator cuff, which lift, rotate and stabilise the arm at the shoulder joint.", [
        ("Front Delts", "Anterior deltoid. Raises the arm forward; overhead and bench pressing, front raises."),
        ("Side Delts", "Lateral (middle) deltoid. Raises the arm out to the side; lateral raises and upright rows."),
        ("Rear Delts", "Posterior deltoid. Pulls the arm back and out; reverse flyes, face pulls and rows."),
        ("Rotator Cuff", "Supraspinatus, infraspinatus, teres minor and subscapularis. Rotates the arm and keeps the shoulder joint centred; external/internal rotations."),
    ]),
    "Arms": ("Upper arm and forearm muscles that bend and straighten the elbow and control the wrist and grip.", [
        ("Biceps", "Biceps brachii (long and short heads). Bends the elbow and turns the palm up; curls and chin-ups."),
        ("Brachialis", "Lies under the biceps; the strongest elbow flexor regardless of grip. Hammer and reverse curls."),
        ("Brachioradialis", "Forearm muscle on the thumb side. Bends the elbow with a neutral grip; hammer curls and reverse curls."),
        ("Triceps", "Triceps brachii (long, lateral and medial heads). Straightens the elbow; presses, dips, pushdowns and extensions."),
        ("Forearm Flexors", "Wrist and finger flexors on the palm side of the forearm. Grip and wrist curls."),
        ("Forearm Extensors", "Wrist and finger extensors on the back of the forearm. Reverse wrist curls and grip balance."),
    ]),
    "Core": ("Muscles of the trunk that brace, bend, rotate and stabilise the spine and pelvis.", [
        ("Abs", "Rectus abdominis, the \"six-pack\". Flexes the spine and resists extension; crunches, leg raises, rollouts."),
        ("Obliques", "External and internal obliques on the sides of the waist. Rotate and side-bend the trunk and resist rotation; woodchops, side planks, Pallof presses."),
        ("Transverse Abdominis", "Deepest abdominal layer. Draws the belly in and braces the trunk; vacuums, dead bugs and heavy bracing."),
        ("Quadratus Lumborum", "Deep lower-back muscle between the pelvis and ribs. Side-bends and stabilises the spine; suitcase carries and side planks."),
    ]),
    "Glutes": ("Hip muscles of the buttocks that extend, abduct and rotate the hip.", [
        ("Gluteus Maximus", "The largest glute. Extends the hip; squats, deadlifts, hip thrusts and lunges."),
        ("Gluteus Medius", "Upper outer glute. Abducts the hip and keeps the pelvis level on one leg; side-lying raises, single-leg work."),
        ("Gluteus Minimus", "Under the glute medius; assists hip abduction and internal rotation and stabilises the hip."),
        ("Tensor Fasciae Latae", "TFL, at the front-outer hip, feeding the IT band. Assists hip flexion and abduction."),
        ("Deep Hip Rotators", "Piriformis and the other small external rotators of the hip. Rotate the thigh outward and stabilise the hip; clamshells, banded walks."),
    ]),
    "Legs": ("Thigh, hip flexor and lower-leg muscles that drive the knee, ankle and hip.", [
        ("Quadriceps", "Rectus femoris and the three vastus muscles on the front of the thigh. Straighten the knee; squats, lunges, leg presses and extensions."),
        ("Hamstrings", "Biceps femoris, semitendinosus and semimembranosus on the back of the thigh. Bend the knee and extend the hip; RDLs, leg curls, Nordics."),
        ("Adductors", "Adductor magnus, longus and brevis plus gracilis on the inner thigh. Bring the leg in and help extend the hip; wide squats, Copenhagen planks."),
        ("Hip Flexors", "Iliopsoas (iliacus and psoas major). Lift the thigh toward the trunk; leg raises, sprinting, mountain climbers."),
        ("Gastrocnemius", "The upper, two-headed calf muscle. Points the foot and assists knee flexion; straight-leg calf raises, jumping."),
        ("Soleus", "The deep calf muscle under the gastrocnemius. Points the foot, especially with a bent knee; seated calf raises."),
        ("Tibialis Anterior", "Front of the shin. Lifts the toes (dorsiflexion) and controls foot strike; tib raises."),
        ("Peroneals", "Fibularis longus and brevis on the outer lower leg. Turn the foot outward and stabilise the ankle."),
    ]),
    "Neck": ("Muscles that flex, extend, rotate and stabilise the head and neck.", [
        ("Sternocleidomastoid", "The large diagonal muscle on each side of the front of the neck. Flexes and rotates the head; neck curls and harness work."),
        ("Neck Extensors", "Splenius capitis/cervicis and the other muscles on the back of the neck. Extend the head and hold posture; neck extensions."),
        ("Levator Scapulae", "Runs from the upper neck to the top of the shoulder blade. Elevates the shoulder blade and side-bends the neck."),
        ("Scalenes", "On the side of the neck. Side-bend the neck and lift the upper ribs during heavy breathing; lateral neck work."),
    ]),
}


def seed(db: TrainerDB, reset: bool = False) -> None:
    if reset:
        db.db.muscles.delete_many({})
        db.db.muscle_groups.delete_many({})
        db.db.exercises.update_many({}, {"$unset": {field: "" for field in MUSCLE_FIELDS + ADDED_GROUP_FIELDS + GROUP_FIELDS}})
    groups = {group["name"].lower(): str(group["_id"]) for group in db.get_all_muscle_groups()}
    muscles = {muscle["name"].lower() for muscle in db.get_all_muscles()}
    added = 0
    for group_name, (description, members) in GROUPS.items():
        group_id = groups.get(group_name.lower()) or db.add_muscle_group({"name": group_name, "description": description})
        for name, muscle_description in members:
            if name.lower() not in muscles:
                db.add_muscle({"name": name, "description": muscle_description, "group_id": group_id})
                added += 1
    print(f"{len(GROUPS)} groups, {added} muscles added")


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if arg != "--reset"]
    trainer_db = TrainerDB(*args)
    trainer_db.ensure_indexes()
    seed(trainer_db, reset="--reset" in sys.argv)
