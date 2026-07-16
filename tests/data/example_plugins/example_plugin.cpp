#include <rpp_plugin_types/rpp_common/MotionController2D.hpp>
#include <rpp_schema/rpp_common/Path2D.hpp>
#include <rpp_schema/rpp_common/Command.hpp>


std::map<std::string, std::string> COMPONENTS = {
    {"ctl1", "rpp_common::MotionController2D"},
};

class ComponentPlugin : public rpp_common::MotionController2D
{

public:
    ComponentPlugin() = default;

    virtual ~ComponentPlugin() = default;

    rpp_common::MotionController2D::VectorPlanar::Const step(rpp_common::MotionController2D::Pose2D::Const state, double dt) override
    {

        rpp_schema::rpp_common::Path2D path;
        path.points().init(2);
        path.points()[0].x() = 1.0;
        path.points()[0].y() = 2.0;
        path.points()[1].x() = 3.0;
        path.points()[1].y() = 4.0;

        auto point_as_struct = path.points()[1].as_struct();

        rpp_schema::rpp_common::Command command;

        command.data().init(2);
        command.data()[0] = 0.0;
        command.data()[1] = 1.0;

        VectorPlanar vector;
        vector.x() = point_as_struct.x;
        vector.y() = command.data()[1];
        vector.yaw() = 3.14;
        return std::move(vector);
    }

    bool validate(rpp_common::MotionController2D::Pose2D::Const state) override
    {
        auto x = state.position().x();
        return x > 5.0;
    }

};


